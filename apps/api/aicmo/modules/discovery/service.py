"""Discovery service — create runs, poll, and apply the draft to the Brand
Brain.

Apply writes to the SAME `business_profiles` row the Brand Brain reads from
(via onboarding), sets `analysis_status='pending'` so the existing analyzer
enriches it, and audits the change. No Brand Brain logic is duplicated — the
draft's fields map straight onto the existing profile columns.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.discovery.models import WebsiteDiscovery
from aicmo.modules.discovery.schemas import (
    ApplyDiscovery,
    DiscoveryDraft,
    DiscoveryResponse,
    StartScratchDiscovery,
    StartWebsiteDiscovery,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Pick a workspace first, then we can learn about your business.",
        )
    return tenant.brand_id


def _to_response(row: WebsiteDiscovery) -> DiscoveryResponse:
    draft = DiscoveryDraft.model_validate(row.draft) if row.draft else None
    return DiscoveryResponse(
        id=row.id,
        source=row.source,  # type: ignore[arg-type]
        url=row.url,
        business_name=row.business_name,
        industry=row.industry,
        status=row.status,  # type: ignore[arg-type]
        stage=row.stage,  # type: ignore[arg-type]
        draft=draft,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_website(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartWebsiteDiscovery,
) -> WebsiteDiscovery:
    brand_id = _require_brand(tenant)
    row = WebsiteDiscovery(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        created_by_user_id=tenant.user_uuid,
        source="website",
        url=payload.website_url.strip(),
        business_name=payload.business_name.strip(),
        industry=payload.industry.strip(),
        status="pending",
    )
    session.add(row)
    await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        actor_user_id=tenant.user_uuid,
        action="discovery.started",
        target_type="discovery",
        target_id=row.id,
        after={"source": "website", "url": row.url},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def create_scratch(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartScratchDiscovery,
) -> WebsiteDiscovery:
    brand_id = _require_brand(tenant)
    row = WebsiteDiscovery(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        created_by_user_id=tenant.user_uuid,
        source="scratch",
        business_name=payload.business_name.strip(),
        industry=(payload.industry or "").strip() or None,
        status="pending",
        seed=payload.model_dump(),
    )
    session.add(row)
    await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        actor_user_id=tenant.user_uuid,
        action="discovery.started",
        target_type="discovery",
        target_id=row.id,
        after={"source": "scratch"},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def get(
    session: AsyncSession, *, tenant: TenantContext, discovery_id: uuid.UUID
) -> WebsiteDiscovery:
    brand_id = _require_brand(tenant)
    row = await session.get(WebsiteDiscovery, discovery_id)
    if row is None or row.brand_id != brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discovery not found")
    return row


async def apply(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    discovery_id: uuid.UUID,
    payload: ApplyDiscovery,
) -> bool:
    """Write the reviewed draft onto the brand's Brand Brain profile
    (create or update). Returns whether analysis should be (re)run.

    The draft is user-approved, so it bypasses the raw-onboarding input
    validators and writes columns directly on the shared profile row."""
    brand_id = _require_brand(tenant)
    row = await get(session, tenant=tenant, discovery_id=discovery_id)
    draft = payload.draft

    existing = await onboarding_service.get_profile_or_none(session, brand_id)
    name = (payload.business_name or row.business_name or "My business").strip()
    industry = (payload.industry or row.industry or "General").strip() or "General"
    website = (payload.website or row.url or None)
    audience = draft.target_audience.strip() or "Customers in my area."
    tone = draft.brand_tone.strip() or "friendly"
    platforms = _platforms_from(row) or ["instagram", "facebook"]
    goals = draft.goals or ["Grow my business"]

    columns = dict(
        business_name=name,
        website=website,
        industry=industry,
        target_audience=audience,
        brand_tone=tone,
        preferred_platforms=platforms,
        competitors=draft.competitors,
        goals=goals,
        products=draft.products,
        services=draft.services,
        unique_selling_points=draft.unique_selling_points,
        keywords=draft.keywords,
        brand_colors=draft.brand_colors,
        fonts=draft.fonts,
        brand_rules=draft.brand_rules,
        writing_style=draft.writing_style or None,
    )

    if existing is None:
        profile = BusinessProfile(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=brand_id,
            analysis_status="pending",
            analysis=None,
            analysis_error=None,
            **columns,
        )
        session.add(profile)
    else:
        for key, value in columns.items():
            setattr(existing, key, value)
        existing.analysis_status = "pending"
        existing.analysis = None
        existing.analysis_error = None

    row.status = "completed"
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        actor_user_id=tenant.user_uuid,
        action="brand.brain_applied",
        target_type="brand",
        target_id=brand_id,
        after={"source": row.source, "discovery_id": str(discovery_id)},
    )
    await session.commit()
    return True


def _platforms_from(row: WebsiteDiscovery) -> list[str]:
    """Preferred platforms seeded from social links found on the site."""
    signals = row.signals or {}
    socials = signals.get("social_links") or {}
    return list(socials.keys())[:6]
