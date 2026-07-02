"""Content business logic.

Post W1-12: every public function takes `tenant: TenantContext`. Lookups
filter by `brand_id`. INSERTs populate `organization_id` + `brand_id` from
the tenant. `user_id` is still written to the legacy column for audit.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.distribution.url_builder import (
    MEDIUM_BY_CONTENT_TYPE,
    maybe_share_url,
)
from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_CONTENT,
    ACTION_GENERATE_REEL,
    record_ai_generation,
)
from aicmo.modules.billing import billing_live
from aicmo.modules.content.generator import generate_content
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.content.schemas import (
    NON_PLATFORM_TYPES,
    GeneratedContentResponse,
    GenerateRequest,
)
from aicmo.modules.content.templates import effective_tone
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.landing_pages import service as landing_pages_service
from aicmo.modules.learning.recorder import record_generation
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.performance.tagging import resolve_creative_tags
from aicmo.modules.trends import service as trends_service
from aicmo.modules.trends.schemas import TrendAnalysis
from aicmo.tenancy.context import TenantContext


async def _validate_link_ownership(
    session: AsyncSession, *, tenant: TenantContext, payload: GenerateRequest
) -> None:
    """Phase 6.2 — every provided traceability link (campaign/bundle/strategy/
    recommendation) must belong to THIS tenant's brand. Rejects unknown or
    cross-tenant IDs (IDOR-safe). Lazy imports avoid an import cycle."""
    from aicmo.modules.advisor.models import AdvisorRecommendation
    from aicmo.modules.bundles.models import Bundle
    from aicmo.modules.campaigns.models import CampaignPlan
    from aicmo.modules.strategist.models import MarketingStrategyRecord

    checks = (
        (payload.campaign_id, CampaignPlan, "Campaign"),
        (payload.bundle_id, Bundle, "Bundle"),
        (payload.strategy_id, MarketingStrategyRecord, "Strategy"),
        (payload.recommendation_id, AdvisorRecommendation, "Recommendation"),
    )
    for id_, model, label in checks:
        if id_ is None:
            continue
        row = await session.get(model, id_)
        if row is None or getattr(row, "brand_id", None) != tenant.brand_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} not found in this workspace.",
            )


async def generate(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: GenerateRequest,
) -> GeneratedContentResponse:
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before generating content",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)

    # Phase 1 — soft usage gate (record-only until enforcement enabled).
    await billing_live.enforce_quota(
        session, organization_id=tenant.organization_id, kind="generation"
    )

    if (
        payload.content_type not in NON_PLATFORM_TYPES
        and payload.platform not in profile.preferred_platforms
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.platform}' is not one of your preferred platforms",
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

    # Phase 6.2 — validate optional traceability links before doing any work.
    await _validate_link_ownership(session, tenant=tenant, payload=payload)

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
    except Exception:
        context = None

    strategy, output, _in_tok, _out_tok = await generate_content(
        content_type=payload.content_type,
        profile=profile,
        trend_analysis=trend_analysis,
        platform=payload.platform,
        goal=payload.goal,
        tone_override=payload.tone,
        context=context,
        recommendation_context=payload.recommendation_context,
    )

    # Phase 9.1 — Performance Intelligence tag derivation.
    strategy_text = " ".join(
        v for v in [
            getattr(strategy, "hook", None),
            getattr(strategy, "audience_angle", None),
            getattr(strategy, "why_it_works", None),
        ] if isinstance(v, str)
    )
    tags = resolve_creative_tags(
        goal=payload.goal,
        audience=getattr(strategy, "audience_angle", None),
        platform=payload.platform,
        strategy_text=strategy_text,
        tone=effective_tone(profile.brand_tone, payload.tone),
    )

    row = GeneratedContent(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        trend_report_id=trend_report_id,
        landing_page_id=payload.landing_page_id,
        campaign_id=payload.campaign_id,
        bundle_id=payload.bundle_id,
        strategy_id=payload.strategy_id,
        recommendation_id=payload.recommendation_id,
        content_type=payload.content_type,
        platform=payload.platform,
        goal=payload.goal,
        tone=effective_tone(profile.brand_tone, payload.tone),
        strategy=strategy.model_dump(mode="json"),
        output=output,
        concept_family=tags.get("concept_family"),
        emotion=tags.get("emotion"),
        audience=tags.get("audience"),
        funnel_stage=tags.get("funnel_stage"),
        business_goal=tags.get("business_goal"),
        offer_type=tags.get("offer_type"),
        is_saved=False,
    )
    session.add(row)
    await record_generation(
        session,
        tenant=tenant,
        source_asset_type="content",
        source_asset_id=row.id,
        platform=payload.platform,
        goal=payload.goal,
        variable_choices={
            "content_type": payload.content_type,
            "platform": payload.platform,
            "tone": effective_tone(profile.brand_tone, payload.tone),
            "trend_grounded": trend_analysis is not None,
            "has_landing_page": payload.landing_page_id is not None,
        },
        hypothesis=getattr(strategy, "audience_angle", None),
        context=context,
    )
    # Phase S-AI-AUDIT — security/compliance audit. reel uses a distinct
    # action so investigators can filter video generations.
    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=(
            ACTION_GENERATE_REEL
            if payload.content_type == "reel"
            else ACTION_GENERATE_CONTENT
        ),
        asset_id=row.id,
        model_used=get_settings().llm_default_model,
        metadata={
            "content_type": payload.content_type,
            "platform": payload.platform,
            "trend_grounded": trend_analysis is not None,
            "has_landing_page": payload.landing_page_id is not None,
        },
    )
    await billing_live.record_metered(
        session,
        organization_id=tenant.organization_id,
        kind="generation",
        user_id=tenant.user_uuid,
        brand_id=tenant.brand_id,
        metadata={"asset_type": "content", "content_type": payload.content_type},
    )
    from aicmo.modules.publishing import assets as publishing_assets

    await publishing_assets.register_from_content(
        session,
        tenant=tenant,
        content_id=row.id,
        content_type=payload.content_type,
        platform=payload.platform,
        output=output,
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row, landing_slug=landing_slug)


async def list_content(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    saved_only: bool,
    content_type: str | None,
    limit: int,
) -> list[GeneratedContentResponse]:
    stmt = (
        select(GeneratedContent)
        .where(GeneratedContent.brand_id == tenant.brand_id)
        .order_by(desc(GeneratedContent.created_at))
        .limit(min(max(limit, 1), 100))
    )
    if saved_only:
        stmt = stmt.where(GeneratedContent.is_saved.is_(True))
    if content_type:
        stmt = stmt.where(GeneratedContent.content_type == content_type)
    rows = (await session.execute(stmt)).scalars().all()
    slugs = await _slug_lookup(
        session, tenant.brand_id, [r.landing_page_id for r in rows]
    )
    return [_to_response(r, landing_slug=slugs.get(r.landing_page_id)) for r in rows]


async def get_one(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> GeneratedContentResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, content_id=content_id)
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
    content_id: uuid.UUID,
    is_saved: bool,
) -> GeneratedContentResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, content_id=content_id)
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


async def delete_content(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, content_id=content_id)
    await session.delete(row)
    await session.commit()


# ----------------- internals -----------------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, content_id: uuid.UUID
) -> GeneratedContent:
    stmt = select(GeneratedContent).where(
        GeneratedContent.id == content_id,
        GeneratedContent.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated content not found",
        )
    return row


async def _slug_lookup(
    session: AsyncSession,
    brand_id: uuid.UUID,
    page_ids: list[uuid.UUID | None],
) -> dict[uuid.UUID, str]:
    """Batch-load slugs for a set of landing_page_ids in this brand."""
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


def _to_response(
    row: GeneratedContent, *, landing_slug: str | None = None
) -> GeneratedContentResponse:
    base = GeneratedContentResponse.model_validate(row)
    base.share_url = maybe_share_url(
        slug=landing_slug,
        asset_type="content",
        asset_id=row.id,
        platform=row.platform,
        medium_override=MEDIUM_BY_CONTENT_TYPE.get(row.content_type),
        utm_content_override=row.content_type,
    )
    return base
