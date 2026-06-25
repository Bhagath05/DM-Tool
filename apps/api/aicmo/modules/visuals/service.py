"""Visual-brief business logic. Post W1-12: brand-scoped."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.distribution.url_builder import maybe_share_url
from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_CREATIVE,
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
from aicmo.modules.visuals.generator import generate_visual
from aicmo.modules.visuals.models import GeneratedVisual
from aicmo.modules.visuals.render import auto_render_visual, latest_renders_for_visuals
from aicmo.modules.visuals.render_schemas import RenderedVisualResponse
from aicmo.modules.visuals.schemas import (
    GeneratedVisualResponse,
    GenerateVisualRequest,
)
from aicmo.modules.visuals.templates import effective_tone
from aicmo.tenancy.context import TenantContext


async def generate(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: GenerateVisualRequest,
) -> GeneratedVisualResponse:
    profile_row = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before generating visuals",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)

    # Phase 1 — soft usage gate (record-only until enforcement enabled).
    await billing_live.enforce_quota(
        session, organization_id=tenant.organization_id, kind="generation"
    )

    if payload.platform not in profile.preferred_platforms:
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

    strategy, output, _in_tok, _out_tok = await generate_visual(
        visual_type=payload.visual_type,
        profile=profile,
        trend_analysis=trend_analysis,
        platform=payload.platform,
        goal=payload.goal,
        tone_override=payload.tone,
        context=context,
        recommendation_context=payload.recommendation_context,
    )

    # Phase 9.1 — derive Performance Intelligence tags from the
    # generation inputs + strategy output. Never raises; missing
    # signals just leave columns NULL.
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

    row = GeneratedVisual(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        trend_report_id=trend_report_id,
        landing_page_id=payload.landing_page_id,
        visual_type=payload.visual_type,
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
        source_asset_type="visual",
        source_asset_id=row.id,
        platform=payload.platform,
        goal=payload.goal,
        variable_choices={
            "visual_type": payload.visual_type,
            "platform": payload.platform,
            "tone": effective_tone(profile.brand_tone, payload.tone),
            "trend_grounded": trend_analysis is not None,
            "has_landing_page": payload.landing_page_id is not None,
        },
        hypothesis=getattr(strategy, "audience_angle", None),
        context=context,
    )
    # Phase S-AI-AUDIT — security/compliance audit.
    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=ACTION_GENERATE_CREATIVE,
        asset_id=row.id,
        model_used=get_settings().llm_default_model,
        metadata={
            "visual_type": payload.visual_type,
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
        metadata={"asset_type": "visual", "visual_type": payload.visual_type},
    )
    await session.flush()
    renders = await auto_render_visual(
        session, tenant=tenant, visual=row, profile=profile
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row, landing_slug=landing_slug, renders=renders)


async def list_visuals(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    saved_only: bool,
    visual_type: str | None,
    limit: int,
) -> list[GeneratedVisualResponse]:
    stmt = (
        select(GeneratedVisual)
        .where(GeneratedVisual.brand_id == tenant.brand_id)
        .order_by(desc(GeneratedVisual.created_at))
        .limit(min(max(limit, 1), 100))
    )
    if saved_only:
        stmt = stmt.where(GeneratedVisual.is_saved.is_(True))
    if visual_type:
        stmt = stmt.where(GeneratedVisual.visual_type == visual_type)
    rows = (await session.execute(stmt)).scalars().all()
    slugs = await _slug_lookup(session, tenant.brand_id, [r.landing_page_id for r in rows])
    render_map = await latest_renders_for_visuals(
        session, brand_id=tenant.brand_id, visual_ids=[r.id for r in rows]
    )
    return [
        _to_response(
            r,
            landing_slug=slugs.get(r.landing_page_id),
            renders=render_map.get(r.id, []),
        )
        for r in rows
    ]


async def get_one(
    session: AsyncSession, *, tenant: TenantContext, visual_id: uuid.UUID
) -> GeneratedVisualResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, visual_id=visual_id)
    slug = (
        await landing_pages_service.get_owned_slug(
            session, brand_id=tenant.brand_id, page_id=row.landing_page_id
        )
        if row.landing_page_id
        else None
    )
    render_map = await latest_renders_for_visuals(
        session, brand_id=tenant.brand_id, visual_ids=[row.id]
    )
    return _to_response(row, landing_slug=slug, renders=render_map.get(row.id, []))


async def set_saved(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual_id: uuid.UUID,
    is_saved: bool,
) -> GeneratedVisualResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, visual_id=visual_id)
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
    render_map = await latest_renders_for_visuals(
        session, brand_id=tenant.brand_id, visual_ids=[row.id]
    )
    return _to_response(row, landing_slug=slug, renders=render_map.get(row.id, []))


async def delete_visual(
    session: AsyncSession, *, tenant: TenantContext, visual_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, visual_id=visual_id)
    await session.delete(row)
    await session.commit()


# ----------------- internals -----------------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, visual_id: uuid.UUID
) -> GeneratedVisual:
    stmt = select(GeneratedVisual).where(
        GeneratedVisual.id == visual_id,
        GeneratedVisual.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generated visual not found"
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
    row: GeneratedVisual,
    *,
    landing_slug: str | None = None,
    renders: list[RenderedVisualResponse] | None = None,
) -> GeneratedVisualResponse:
    base = GeneratedVisualResponse.model_validate(row)
    base.share_url = maybe_share_url(
        slug=landing_slug,
        asset_type="visual",
        asset_id=row.id,
        platform=row.platform,
        utm_content_override=row.visual_type,
    )
    if renders is not None:
        base.renders = renders
        if renders:
            base.primary_signed_url = renders[0].signed_url
            base.thumbnail_url = renders[0].signed_url
    return base
