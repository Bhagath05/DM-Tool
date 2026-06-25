"""Campaign-planner business logic. Post W1-12: brand-scoped."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.distribution.url_builder import maybe_share_url
from aicmo.modules.campaigns.generator import (
    CampaignDayCountMismatch,
    generate_campaign,
)
from aicmo.modules.campaigns.models import CampaignPlan
from aicmo.modules.campaigns.schemas import (
    CalendarDay,
    CampaignPlanResponse,
    GenerateCampaignRequest,
)
from aicmo.config import get_settings
from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_CAMPAIGN,
    record_ai_generation,
)
from aicmo.modules.billing import billing_live
from aicmo.modules.campaigns.templates import effective_tone
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.landing_pages import service as landing_pages_service
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends import service as trends_service
from aicmo.modules.trends.schemas import TrendAnalysis
from aicmo.tenancy.context import TenantContext


async def generate(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: GenerateCampaignRequest,
) -> CampaignPlanResponse:
    profile_row = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before planning campaigns",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)

    # Phase 1 — soft usage gate (record-only until enforcement enabled).
    await billing_live.enforce_quota(
        session, organization_id=tenant.organization_id, kind="campaign"
    )

    invalid = [p for p in payload.platforms if p not in profile.preferred_platforms]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platforms not in your preferred list: {', '.join(invalid)}",
        )

    landing_slug: str | None = None
    if payload.landing_page_id is not None:
        landing_slug = await landing_pages_service.get_owned_slug(
            session, brand_id=tenant.brand_id, page_id=payload.landing_page_id
        )
        if landing_slug is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Landing page not found or archived",
            )

    trend_row = await trends_service.get_report(session, tenant.brand_id)
    trend_analysis: TrendAnalysis | None = None
    trend_report_id: uuid.UUID | None = None
    if trend_row and trend_row.status == "completed" and trend_row.analysis:
        trend_analysis = TrendAnalysis.model_validate(trend_row.analysis)
        trend_report_id = trend_row.id

    context = None
    try:
        context = await build_generation_context(
            session, profile=profile, brand_id=tenant.brand_id
        )
    except Exception:  # noqa: BLE001
        context = None

    try:
        strategy_envelope, days, _in_tok, _out_tok = await generate_campaign(
            campaign_type=payload.campaign_type,
            duration_days=payload.duration_days,
            platforms=payload.platforms,
            goal=payload.goal,
            tone_override=payload.tone,
            audience_override=payload.audience_override,
            profile=profile,
            trend_analysis=trend_analysis,
            context=context,
        )
    except CampaignDayCountMismatch as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI returned an incomplete plan ({e}). Regenerate to try again.",
        ) from e

    row = CampaignPlan(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        trend_report_id=trend_report_id,
        landing_page_id=payload.landing_page_id,
        campaign_type=payload.campaign_type,
        duration_days=payload.duration_days,
        goal=payload.goal,
        tone=effective_tone(profile.brand_tone, payload.tone),
        strategy=strategy_envelope,
        calendar=[d.model_dump(mode="json") for d in days],
        is_saved=False,
    )
    session.add(row)
    # Phase S-AI-AUDIT — security/compliance audit row.
    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=ACTION_GENERATE_CAMPAIGN,
        asset_id=row.id,
        model_used=get_settings().llm_default_model,
        metadata={
            "campaign_type": payload.campaign_type,
            "duration_days": payload.duration_days,
            "platforms": list(payload.platforms),
            "has_landing_page": payload.landing_page_id is not None,
        },
    )
    await billing_live.record_metered(
        session,
        organization_id=tenant.organization_id,
        kind="campaign",
        user_id=tenant.user_uuid,
        brand_id=tenant.brand_id,
        metadata={"campaign_type": payload.campaign_type},
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row, landing_slug=landing_slug)


async def list_campaigns(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    saved_only: bool,
    campaign_type: str | None,
    limit: int,
) -> list[CampaignPlanResponse]:
    stmt = (
        select(CampaignPlan)
        .where(CampaignPlan.brand_id == tenant.brand_id)
        .order_by(desc(CampaignPlan.created_at))
        .limit(min(max(limit, 1), 100))
    )
    if saved_only:
        stmt = stmt.where(CampaignPlan.is_saved.is_(True))
    if campaign_type:
        stmt = stmt.where(CampaignPlan.campaign_type == campaign_type)
    rows = (await session.execute(stmt)).scalars().all()
    slugs = await _slug_lookup(session, tenant.brand_id, [r.landing_page_id for r in rows])
    return [_to_response(r, landing_slug=slugs.get(r.landing_page_id)) for r in rows]


async def get_one(
    session: AsyncSession, *, tenant: TenantContext, campaign_id: uuid.UUID
) -> CampaignPlanResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, campaign_id=campaign_id)
    slug = (
        await landing_pages_service.get_owned_slug(
            session, brand_id=tenant.brand_id, page_id=row.landing_page_id
        )
        if row.landing_page_id
        else None
    )
    return _to_response(row, landing_slug=slug)


async def set_saved(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    campaign_id: uuid.UUID,
    is_saved: bool,
) -> CampaignPlanResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, campaign_id=campaign_id)
    row.is_saved = is_saved
    await session.commit()
    await session.refresh(row)
    slug = (
        await landing_pages_service.get_owned_slug(
            session, brand_id=tenant.brand_id, page_id=row.landing_page_id
        )
        if row.landing_page_id
        else None
    )
    return _to_response(row, landing_slug=slug)


async def delete_campaign(
    session: AsyncSession, *, tenant: TenantContext, campaign_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, campaign_id=campaign_id)
    await session.delete(row)
    await session.commit()


# ----------------- internals -----------------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, campaign_id: uuid.UUID
) -> CampaignPlan:
    stmt = select(CampaignPlan).where(
        CampaignPlan.id == campaign_id,
        CampaignPlan.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign plan not found"
        )
    return row


async def _slug_lookup(
    session: AsyncSession,
    brand_id: uuid.UUID,
    page_ids: list[uuid.UUID | None],
) -> dict[uuid.UUID, str]:
    from aicmo.modules.landing_pages.models import LandingPage

    ids = {pid for pid in page_ids if pid is not None}
    if not ids:
        return {}
    stmt = select(LandingPage.id, LandingPage.slug).where(
        LandingPage.brand_id == brand_id,
        LandingPage.is_archived.is_(False),
        LandingPage.id.in_(ids),
    )
    rows = (await session.execute(stmt)).all()
    return {r.id: r.slug for r in rows}


def _build_day_share_urls(
    *, row: CampaignPlan, landing_slug: str | None
) -> dict[str, str]:
    if landing_slug is None:
        return {}
    out: dict[str, str] = {}
    for raw in row.calendar or []:
        day = CalendarDay.model_validate(raw)
        url = maybe_share_url(
            slug=landing_slug,
            asset_type="campaign",
            asset_id=row.id,
            platform=day.platform,
            utm_content_override=f"day_{day.day}",
        )
        if url is not None:
            out[str(day.day)] = url
    return out


def _to_response(
    row: CampaignPlan, *, landing_slug: str | None = None
) -> CampaignPlanResponse:
    base = CampaignPlanResponse.model_validate(row)
    base.share_urls = _build_day_share_urls(row=row, landing_slug=landing_slug)
    return base
