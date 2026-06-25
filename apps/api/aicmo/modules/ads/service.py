"""Ads business logic.

Post W1-12: brand-scoped. INSERTs populate org_id + brand_id.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.distribution.url_builder import MEDIUM_BY_AD_TYPE, maybe_share_url
from aicmo.modules.ads.generator import generate_ad
from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.ads.schemas import (
    PLATFORM_BY_AD_TYPE,
    GenerateAdRequest,
    GeneratedAdResponse,
)
from aicmo.modules.ads.templates import effective_tone
from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_AD,
    record_ai_generation,
)
from aicmo.modules.billing import billing_live
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.landing_pages import service as landing_pages_service
from aicmo.modules.learning.recorder import record_generation
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.performance.tagging import resolve_creative_tags
from aicmo.modules.trends import service as trends_service
from aicmo.modules.trends.schemas import TrendAnalysis
from aicmo.modules.visuals.media_url import make_signed_url
from aicmo.modules.visuals.render import render_ad_image
from aicmo.modules.visuals.render_prompt import ad_output_to_brief
from aicmo.modules.visuals.render_schemas import RenderedVisualResponse
from aicmo.tenancy.context import TenantContext


async def generate(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: GenerateAdRequest,
) -> GeneratedAdResponse:
    profile_row = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before generating ads",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)

    # Phase 1 — soft usage gate. No-op (record-only) until enforcement is
    # enabled; Early Access (no quota) short-circuits. Never blocks today.
    await billing_live.enforce_quota(
        session, organization_id=tenant.organization_id, kind="generation"
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
    except Exception:
        context = None

    strategy, targeting, output, _in_tok, _out_tok = await generate_ad(
        ad_type=payload.ad_type,
        objective=payload.objective,
        profile=profile,
        trend_analysis=trend_analysis,
        goal=payload.goal,
        tone_override=payload.tone,
        audience_override=payload.audience_override,
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
    audience_text = payload.audience_override or getattr(
        strategy, "audience_angle", None
    )
    tags = resolve_creative_tags(
        goal=payload.goal,
        audience=audience_text,
        platform=PLATFORM_BY_AD_TYPE[payload.ad_type],
        funnel_stage=payload.objective,
        strategy_text=strategy_text,
        tone=effective_tone(profile.brand_tone, payload.tone),
    )

    row = GeneratedAd(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        trend_report_id=trend_report_id,
        landing_page_id=payload.landing_page_id,
        ad_type=payload.ad_type,
        platform=PLATFORM_BY_AD_TYPE[payload.ad_type],
        objective=payload.objective,
        goal=payload.goal,
        tone=effective_tone(profile.brand_tone, payload.tone),
        strategy=strategy.model_dump(mode="json"),
        targeting=targeting.model_dump(mode="json"),
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
        source_asset_type="ad",
        source_asset_id=row.id,
        platform=PLATFORM_BY_AD_TYPE[payload.ad_type],
        goal=payload.goal,
        variable_choices={
            "ad_type": payload.ad_type,
            "objective": payload.objective,
            "tone": effective_tone(profile.brand_tone, payload.tone),
            "audience_override": payload.audience_override,
            "trend_grounded": trend_analysis is not None,
            "has_landing_page": payload.landing_page_id is not None,
        },
        hypothesis=getattr(strategy, "audience_angle", None),
        context=context,
    )
    # Phase S-AI-AUDIT — security/compliance audit row. Distinct from the
    # learning recorder above. Stores NO generated content.
    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=ACTION_GENERATE_AD,
        asset_id=row.id,
        model_used=get_settings().llm_default_model,
        metadata={
            "ad_type": payload.ad_type,
            "objective": payload.objective,
            "platform": PLATFORM_BY_AD_TYPE[payload.ad_type],
            "has_landing_page": payload.landing_page_id is not None,
            "trend_grounded": trend_analysis is not None,
        },
    )
    # Phase 1 — meter the generation (best-effort, same TX).
    await billing_live.record_metered(
        session,
        organization_id=tenant.organization_id,
        kind="generation",
        user_id=tenant.user_uuid,
        brand_id=tenant.brand_id,
        metadata={"asset_type": "ad", "ad_type": payload.ad_type},
    )
    await session.flush()
    brief_output = ad_output_to_brief(ad_type=payload.ad_type, output=output)
    rendered = await render_ad_image(
        session,
        tenant=tenant,
        profile=profile,
        brief_output=brief_output,
        ad_strategy=strategy.model_dump(mode="json"),
        platform=PLATFORM_BY_AD_TYPE[payload.ad_type],
        goal=payload.goal,
        tone=effective_tone(profile.brand_tone, payload.tone),
        business_profile_id=profile.id,
        trend_report_id=trend_report_id,
        landing_page_id=payload.landing_page_id,
    )
    if rendered is not None:
        row.rendered_visual_id = rendered.id
    await session.commit()
    await session.refresh(row)
    return _to_response(row, landing_slug=landing_slug, rendered=rendered)


async def list_ads(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    saved_only: bool,
    ad_type: str | None,
    objective: str | None,
    limit: int,
) -> list[GeneratedAdResponse]:
    stmt = (
        select(GeneratedAd)
        .where(GeneratedAd.brand_id == tenant.brand_id)
        .order_by(desc(GeneratedAd.created_at))
        .limit(min(max(limit, 1), 100))
    )
    if saved_only:
        stmt = stmt.where(GeneratedAd.is_saved.is_(True))
    if ad_type:
        stmt = stmt.where(GeneratedAd.ad_type == ad_type)
    if objective:
        stmt = stmt.where(GeneratedAd.objective == objective)
    rows = (await session.execute(stmt)).scalars().all()
    slugs = await _slug_lookup(session, tenant.brand_id, [r.landing_page_id for r in rows])
    image_urls = await _image_urls_for_ads(session, rows)
    return [
        _to_response(
            r,
            landing_slug=slugs.get(r.landing_page_id),
            primary_image_url=image_urls.get(r.id),
        )
        for r in rows
    ]


async def get_one(
    session: AsyncSession, *, tenant: TenantContext, ad_id: uuid.UUID
) -> GeneratedAdResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, ad_id=ad_id)
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
    ad_id: uuid.UUID,
    is_saved: bool,
) -> GeneratedAdResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, ad_id=ad_id)
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


async def delete_ad(
    session: AsyncSession, *, tenant: TenantContext, ad_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, ad_id=ad_id)
    await session.delete(row)
    await session.commit()


# ----------------- internals -----------------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, ad_id: uuid.UUID
) -> GeneratedAd:
    stmt = select(GeneratedAd).where(
        GeneratedAd.id == ad_id,
        GeneratedAd.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generated ad not found"
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


def _to_response(
    row: GeneratedAd,
    *,
    landing_slug: str | None = None,
    rendered: RenderedVisualResponse | None = None,
    primary_image_url: str | None = None,
) -> GeneratedAdResponse:
    base = GeneratedAdResponse.model_validate(row)
    base.share_url = maybe_share_url(
        slug=landing_slug,
        asset_type="ad",
        asset_id=row.id,
        platform=row.platform,
        medium_override=MEDIUM_BY_AD_TYPE.get(row.ad_type),
        utm_content_override=row.ad_type,
    )
    if rendered is not None:
        base.primary_image_url = rendered.signed_url
    elif primary_image_url is not None:
        base.primary_image_url = primary_image_url
    elif row.rendered_visual_id is not None:
        base.primary_image_url = make_signed_url(row.rendered_visual_id)
    return base


async def _image_urls_for_ads(
    session: AsyncSession, rows: list[GeneratedAd]
) -> dict[uuid.UUID, str]:
    from aicmo.modules.visuals.render_models import RenderedVisual

    render_ids = [r.rendered_visual_id for r in rows if r.rendered_visual_id]
    if not render_ids:
        return {}
    stmt = select(RenderedVisual.id).where(RenderedVisual.id.in_(render_ids))
    found = {rid for rid in (await session.execute(stmt)).scalars().all()}
    out: dict[uuid.UUID, str] = {}
    for row in rows:
        if row.rendered_visual_id and row.rendered_visual_id in found:
            out[row.id] = make_signed_url(row.rendered_visual_id)
    return out
