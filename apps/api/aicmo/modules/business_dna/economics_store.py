"""Persistence for Business Economics (Phase 7.20 Stage 2b).

Reads/writes the ``business_profiles.economics`` JSONB column ONLY — it never
touches the AI-generated ``analysis`` column, so re-analysis of a profile cannot
erase economics. All access is tenant- and brand-scoped via ``TenantContext``.

The merge is the Stage 2b safety guarantee: a model-derived (SYSTEM_INFERRED)
incoming value NEVER overwrites a stored USER_STATED / VERIFIED value. A user or a
verified source can always correct any field; a measured value may update a
derived one.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Pick a workspace first, then we can save its economics.",
        )
    return tenant.brand_id


def economics_from_row(profile_row) -> BusinessEconomics | None:
    """Parse the stored JSONB → ``BusinessEconomics``, or None when absent/invalid.
    Never raises — a corrupt/legacy blob is treated as 'no economics yet' so a read
    path (e.g. the DNA facet) degrades gracefully instead of 500-ing."""
    raw = getattr(profile_row, "economics", None) if profile_row is not None else None
    if not raw:
        return None
    try:
        return BusinessEconomics.model_validate(raw)
    except ValidationError:
        log.warning("business_dna.economics_blob_invalid")
        return None


def _merge_value(existing: EconomicValue | None, incoming: EconomicValue | None) -> EconomicValue | None:
    """Field-level merge honouring the no-LLM-overwrite rule."""
    if incoming is None:
        return existing  # no change proposed
    if existing is None:
        return incoming
    # A model-derived value must not clobber a user-provided / verified one.
    from aicmo.modules.business_dna.schemas import ContextProvenance

    if incoming.provenance == ContextProvenance.SYSTEM_INFERRED and existing.is_protected():
        return existing
    return incoming


def merge_economics(existing: BusinessEconomics | None, incoming: BusinessEconomics) -> BusinessEconomics:
    """Merge ``incoming`` onto ``existing``: per-field no-LLM-overwrite for the
    provenance-tagged numeric fields; descriptive/context fields take the incoming
    value when provided. Pure (no I/O); returns a new validated model."""
    base = existing.model_dump() if existing is not None else {}
    merged: dict = dict(base)

    for fname in BusinessEconomics.VALUE_FIELDS:
        kept = _merge_value(
            getattr(existing, fname, None) if existing is not None else None,
            getattr(incoming, fname, None),
        )
        merged[fname] = kept.model_dump() if kept is not None else None

    # Context fields: the incoming value wins when explicitly provided.
    for ctx_field in ("currency", "reporting_period", "revenue_model"):
        val = getattr(incoming, ctx_field)
        if val:
            merged[ctx_field] = val
    if incoming.revenue_streams:
        merged["revenue_streams"] = list(incoming.revenue_streams)

    merged["schema_version"] = incoming.schema_version
    merged.pop("updated_at", None)  # refreshed by default_factory on re-validate
    return BusinessEconomics.model_validate(merged)


async def get_economics(session: AsyncSession, *, tenant: TenantContext) -> BusinessEconomics | None:
    """Return the brand's stored economics, or None. Brand-scoped."""
    brand_id = _require_brand(tenant)
    row = await onboarding_service.get_profile_or_none(session, brand_id)
    return economics_from_row(row)


async def set_economics(
    session: AsyncSession, *, tenant: TenantContext, payload: BusinessEconomics
) -> BusinessEconomics:
    """Validate + merge + persist economics for the active brand.

    Writes ONLY the ``economics`` column, scoped to (organization_id, brand_id) as
    defence in depth. Preserves the no-LLM-overwrite rule and never touches
    ``analysis``. Raises 400 when no profile exists for the brand yet."""
    brand_id = _require_brand(tenant)
    row = await onboarding_service.get_profile_or_none(session, brand_id)
    if row is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Create a business profile before saving economics.",
        )

    existing = economics_from_row(row)
    merged = merge_economics(existing, payload)

    result = await session.execute(
        update(BusinessProfile)
        .where(
            BusinessProfile.id == row.id,
            BusinessProfile.brand_id == brand_id,
            BusinessProfile.organization_id == tenant.organization_id,
        )
        .values(economics=merged.model_dump(mode="json"))
    )
    if getattr(result, "rowcount", 0) != 1:
        # Row vanished or tenant mismatch — fail closed, never cross-write.
        await session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business profile not found for this brand.")
    await session.commit()
    log.info(
        "business_dna.economics_saved",
        organization_id=str(tenant.organization_id),
        brand_id=str(brand_id),
        fields_set=[f for f in BusinessEconomics.VALUE_FIELDS if getattr(merged, f) is not None],
    )
    return merged
