"""Business logic for the onboarding module.

Routes stay thin — they only translate HTTP -> service calls and back.
All validation, DB access, and analysis triggering lives here.

Post W1-12: every public function is brand-scoped. `user_id` from the
TenantContext is still written to the legacy `user_id` column for audit,
but lookups + filtering go through `brand_id`.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.onboarding.schemas import (
    BusinessProfileCreate,
    BusinessProfileResponse,
    BusinessProfileUpdate,
)
from aicmo.tenancy.context import TenantContext


def _to_response(profile: BusinessProfile) -> BusinessProfileResponse:
    return BusinessProfileResponse.model_validate(profile)


async def get_profile_or_none(
    session: AsyncSession, brand_id: uuid.UUID
) -> BusinessProfile | None:
    """Look up the business profile owned by this brand."""
    stmt = select(BusinessProfile).where(BusinessProfile.brand_id == brand_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def require_profile(
    session: AsyncSession, brand_id: uuid.UUID
) -> BusinessProfile:
    profile = await get_profile_or_none(session, brand_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No business profile for this brand",
        )
    return profile


async def create_or_replace_profile(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: BusinessProfileCreate,
) -> tuple[BusinessProfileResponse, bool]:
    """Idempotent on (brand_id): re-submitting onboarding overwrites the
    existing profile and re-runs analysis. Returns (response, created)."""
    if tenant.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brand context required to create a business profile",
        )

    existing = await get_profile_or_none(session, tenant.brand_id)
    created = existing is None

    if existing is None:
        profile = BusinessProfile(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            **_payload_to_columns(payload),
            analysis_status="pending",
            analysis=None,
            analysis_error=None,
        )
        session.add(profile)
    else:
        for key, value in _payload_to_columns(payload).items():
            setattr(existing, key, value)
        existing.analysis_status = "pending"
        existing.analysis = None
        existing.analysis_error = None
        profile = existing

    await session.commit()
    await session.refresh(profile)
    return _to_response(profile), created


async def update_profile(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: BusinessProfileUpdate,
) -> tuple[BusinessProfileResponse, bool]:
    """Partial update. Re-runs analysis only if any analysis-relevant field changed."""
    if tenant.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brand context required",
        )
    profile = await require_profile(session, tenant.brand_id)
    changes = payload.model_dump(exclude_unset=True)
    relevant_changed = any(k in _ANALYSIS_RELEVANT_FIELDS for k in changes)

    for key, value in changes.items():
        if key == "website" and value is not None:
            value = str(value)
        setattr(profile, key, value)

    if relevant_changed:
        profile.analysis_status = "pending"
        profile.analysis = None
        profile.analysis_error = None

    await session.commit()
    await session.refresh(profile)
    return _to_response(profile), relevant_changed


async def delete_profile(
    session: AsyncSession, *, tenant: TenantContext
) -> None:
    if tenant.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brand context required",
        )
    profile = await require_profile(session, tenant.brand_id)
    await session.delete(profile)
    await session.commit()


async def reset_analysis_for_retry(
    session: AsyncSession, *, tenant: TenantContext
) -> BusinessProfileResponse:
    """Flip the profile back to `pending` so a fresh `run_analysis` task can
    overwrite it. Used by the "Try again" button on the dashboard's failure
    card — common when Gemini returns a transient 503 on first run.
    """
    if tenant.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brand context required",
        )
    profile = await require_profile(session, tenant.brand_id)
    profile.analysis_status = "pending"
    profile.analysis = None
    profile.analysis_error = None
    await session.commit()
    await session.refresh(profile)
    return _to_response(profile)


# ---- internals ----


_ANALYSIS_RELEVANT_FIELDS = {
    "business_name",
    "industry",
    "target_audience",
    "brand_tone",
    "competitors",
    "goals",
    "preferred_platforms",
}


def _payload_to_columns(payload: BusinessProfileCreate) -> dict:
    data = payload.model_dump()
    if data.get("website") is not None:
        data["website"] = str(data["website"])
    return data
