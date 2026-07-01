"""Render orchestrator — Phase 4-A + auto-render (Phase 1).

One job: turn a `GeneratedVisual` brief into real PNG(s) on disk,
served by signed URLs. Daily-cap enforced before any provider call.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.creative.storage.base import MediaPersistenceUnavailable
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.visuals.media_url import make_signed_url
from aicmo.modules.visuals.models import GeneratedVisual
from aicmo.modules.visuals.render_models import RenderedVisual
from aicmo.modules.visuals.render_prompt import (
    brief_dict_for_render,
    build_image_prompt,
    build_negative_prompt,
    extract_concept_family,
)
from aicmo.modules.visuals.render_schemas import (
    RenderedVisualResponse,
    RenderQuotaStatus,
)
from aicmo.modules.visuals.schemas import ad_strategy_to_visual_strategy
from aicmo.providers.images import (
    ImageRenderRequest,
    get_image_provider,
)
from aicmo.providers.images.base import AspectRatio
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

_IMAGE_VISUAL_TYPES = frozenset({"ad_creative", "carousel", "thumbnail"})

_ASPECT_FALLBACKS: dict[str, AspectRatio] = {
    "1:1": "1:1",
    "4:5": "4:5",
    "9:16": "9:16",
    "16:9": "16:9",
    "1.91:1": "1.91:1",
}


async def render_visual(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual_id: uuid.UUID,
    quality: str = "standard",
) -> RenderedVisualResponse:
    """Manual re-render endpoint — returns the first/newest PNG."""
    renders = await _render_visual_rows(
        session,
        tenant=tenant,
        visual_id=visual_id,
        quality=quality,
        commit=True,
    )
    if not renders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This visual type does not support image rendering.",
        )
    return renders[0]


async def auto_render_visual(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual: GeneratedVisual,
    profile: BusinessProfileResponse,
    quality: str = "standard",
) -> list[RenderedVisualResponse]:
    """Render immediately after generate — caller owns the transaction commit."""
    if visual.visual_type not in _IMAGE_VISUAL_TYPES:
        return []
    return await _render_visual_rows(
        session,
        tenant=tenant,
        visual_id=visual.id,
        quality=quality,
        commit=False,
        visual=visual,
        profile=profile,
    )


async def render_ad_image(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    profile: BusinessProfileResponse,
    brief_output: dict,
    ad_strategy: dict[str, Any],
    platform: str,
    goal: str,
    tone: str,
    business_profile_id: uuid.UUID,
    trend_report_id: uuid.UUID | None,
    landing_page_id: uuid.UUID | None,
) -> RenderedVisualResponse | None:
    """Create a companion visual row + render one PNG for an ad."""
    focal = brief_output.get("focal_subject") or goal
    visual = GeneratedVisual(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=business_profile_id,
        trend_report_id=trend_report_id,
        landing_page_id=landing_page_id,
        visual_type="ad_creative",
        platform=platform,
        goal=goal,
        tone=tone,
        strategy=ad_strategy_to_visual_strategy(
            ad_strategy, visual_concept=str(focal)
        ),
        output=brief_output,
        is_saved=False,
    )
    session.add(visual)
    await session.flush()
    renders = await auto_render_visual(
        session, tenant=tenant, visual=visual, profile=profile
    )
    return renders[0] if renders else None


async def list_renders(
    session: AsyncSession, *, tenant: TenantContext, visual_id: uuid.UUID
) -> list[RenderedVisualResponse]:
    stmt = (
        select(RenderedVisual)
        .where(
            RenderedVisual.brand_id == tenant.brand_id,
            RenderedVisual.visual_id == visual_id,
        )
        .order_by(
            RenderedVisual.slide_index.asc().nullsfirst(),
            desc(RenderedVisual.created_at),
        )
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


async def get_quota(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> RenderQuotaStatus:
    settings = get_settings()
    cap = settings.image_render_daily_cap
    since = datetime.now(UTC) - timedelta(hours=24)
    stmt = (
        select(func.count())
        .select_from(RenderedVisual)
        .where(
            RenderedVisual.brand_id == brand_id,
            RenderedVisual.created_at >= since,
        )
    )
    used = (await session.execute(stmt)).scalar_one() or 0
    used = int(used)
    return RenderQuotaStatus(
        used_today=used,
        daily_cap=cap,
        remaining=max(cap - used, 0),
    )


async def latest_renders_for_visuals(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    visual_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[RenderedVisualResponse]]:
    """Latest render batch per visual (all carousel slides when applicable)."""
    if not visual_ids:
        return {}
    stmt = (
        select(RenderedVisual)
        .where(
            RenderedVisual.brand_id == brand_id,
            RenderedVisual.visual_id.in_(visual_ids),
        )
        .order_by(RenderedVisual.visual_id, desc(RenderedVisual.created_at))
    )
    rows = (await session.execute(stmt)).scalars().all()
    grouped: dict[uuid.UUID, list[RenderedVisual]] = {}
    for row in rows:
        grouped.setdefault(row.visual_id, []).append(row)

    out: dict[uuid.UUID, list[RenderedVisualResponse]] = {}
    for vid, renders in grouped.items():
        batch = _latest_render_batch(renders)
        out[vid] = [_to_response(r) for r in batch]
    return out


def _latest_render_batch(rows: list[RenderedVisual]) -> list[RenderedVisual]:
    if not rows:
        return []
    latest_at = rows[0].created_at
    batch = [
        r
        for r in rows
        if abs((latest_at - r.created_at).total_seconds()) < 120
    ]
    batch.sort(key=lambda r: (r.slide_index is None, r.slide_index or 0))
    return batch


# ---------------------------------------------------------------------
#  Internals
# ---------------------------------------------------------------------


async def _render_visual_rows(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual_id: uuid.UUID,
    quality: str,
    commit: bool,
    visual: GeneratedVisual | None = None,
    profile: BusinessProfileResponse | None = None,
) -> list[RenderedVisualResponse]:
    if visual is None:
        stmt = select(GeneratedVisual).where(
            GeneratedVisual.id == visual_id,
            GeneratedVisual.brand_id == tenant.brand_id,
        )
        visual = (await session.execute(stmt)).scalar_one_or_none()
        if visual is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Visual brief not found.",
            )

    if visual.visual_type not in _IMAGE_VISUAL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Rendering is not available for '{visual.visual_type}'. "
                "Supported: ad creative, carousel, thumbnail."
            ),
        )

    slide_count = 1
    if visual.visual_type == "carousel":
        slide_count = len((visual.output or {}).get("slide_designs") or [])
        if slide_count == 0:
            slide_count = 1

    quota = await get_quota(session, brand_id=tenant.brand_id)
    if quota.remaining < slide_count:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily render limit reached — need {slide_count} render(s) but "
                f"only {quota.remaining} remain ({quota.daily_cap}/day)."
            ),
        )

    if profile is None:
        profile_row = await onboarding_service.get_profile_or_none(
            session, tenant.brand_id
        )
        if profile_row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete business onboarding before rendering.",
            )
        profile = BusinessProfileResponse.model_validate(profile_row)

    recent_concept_families = await _recent_concept_families(
        session, brand_id=tenant.brand_id, limit=5
    )

    responses: list[RenderedVisualResponse] = []
    indices = (
        range(slide_count)
        if visual.visual_type == "carousel"
        else range(1)
    )
    for slide_index in indices:
        brief = brief_dict_for_render(
            visual_type=visual.visual_type,
            output=visual.output or {},
            slide_index=slide_index if visual.visual_type == "carousel" else None,
        )
        row = await _render_single_png(
            session,
            tenant=tenant,
            visual_id=visual_id,
            visual=visual,
            profile=profile,
            brief=brief,
            quality=quality,
            recent_concept_families=recent_concept_families,
            slide_index=slide_index if visual.visual_type == "carousel" else None,
        )
        responses.append(_to_response(row))
        family = extract_concept_family(row.prompt)
        if family:
            recent_concept_families = (family, *recent_concept_families)[:5]

    if commit:
        await session.commit()

    return responses


async def _render_single_png(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual_id: uuid.UUID,
    visual: GeneratedVisual,
    profile: BusinessProfileResponse,
    brief: dict,
    quality: str,
    recent_concept_families: tuple[str, ...],
    slide_index: int | None,
) -> RenderedVisual:
    settings = get_settings()
    # Production-safety: the visuals store writes PNGs to local disk (media_dir),
    # a separate path from the creative-storage backend. Apply the same gate so
    # ad/creative image rendering can't silently write to ephemeral prod disk.
    # Fail fast BEFORE the paid image-provider call. Lifts when MEDIA_BACKEND=s3/r2.
    if not settings.media_persistence_available:
        raise MediaPersistenceUnavailable(
            "Object storage is not configured (MEDIA_BACKEND=local in production). "
            "Refusing to render an image that would be lost."
        )
    prompt = build_image_prompt(
        brief=brief,
        profile=profile,
        platform=visual.platform,
        visual_type=visual.visual_type,
        recent_concept_families=recent_concept_families,
    )
    negative_prompt = build_negative_prompt(brief=brief)
    fingerprint = hashlib.sha256(
        (prompt + "\n--negative--\n" + negative_prompt).encode("utf-8")
    ).hexdigest()

    aspect_raw = str(brief.get("aspect_ratio") or "1:1")
    aspect: AspectRatio = _ASPECT_FALLBACKS.get(aspect_raw, "1:1")

    try:
        provider = get_image_provider(settings.image_default_provider)
    except Exception as e:
        log.warning("render.provider_init_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_friendly_provider_error(e),
        ) from e

    request = ImageRenderRequest(
        prompt=prompt,
        aspect_ratio=aspect,
        quality="hd" if quality == "hd" else "standard",
        negative_prompt=negative_prompt,
    )
    try:
        result = await provider.render(request)
    except Exception as e:
        log.warning("render.provider_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_friendly_provider_error(e),
        ) from e

    rendered_id = uuid.uuid4()
    file_path = _resolve_path(rendered_id, ".png")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(result.image_bytes)

    row = RenderedVisual(
        id=rendered_id,
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        visual_id=visual_id,
        provider=result.provider_name,
        provider_image_id=result.provider_image_id,
        prompt=prompt,
        prompt_fingerprint=fingerprint,
        file_path=file_path,
        mime_type=result.mime_type,
        width=result.width,
        height=result.height,
        cost_cents=result.cost_cents,
        latency_ms=result.latency_ms,
        slide_index=slide_index,
    )
    session.add(row)
    await session.flush()

    chosen_family = extract_concept_family(prompt)
    log.info(
        "render.completed",
        rendered_id=str(rendered_id),
        visual_id=str(visual_id),
        slide_index=slide_index,
        cost_cents=result.cost_cents,
        latency_ms=result.latency_ms,
        concept_family=chosen_family,
    )
    return row


async def _recent_concept_families(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 5,
) -> tuple[str, ...]:
    stmt = (
        select(RenderedVisual.prompt)
        .where(RenderedVisual.brand_id == brand_id)
        .order_by(desc(RenderedVisual.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    families: list[str] = []
    for stored_prompt in rows:
        family = extract_concept_family(stored_prompt or "")
        if family is not None:
            families.append(family)
    return tuple(families)


def _resolve_path(rendered_id: uuid.UUID, suffix: str) -> str:
    base = get_settings().media_dir
    return os.path.join(base, "renders", f"{rendered_id}{suffix}")


def resolve_file_path(rendered_id: uuid.UUID) -> str:
    return _resolve_path(rendered_id, ".png")


def _to_response(row: RenderedVisual) -> RenderedVisualResponse:
    created = row.created_at or datetime.now(UTC)
    return RenderedVisualResponse(
        id=row.id,
        visual_id=row.visual_id,
        provider=row.provider,
        width=row.width,
        height=row.height,
        mime_type=row.mime_type,
        cost_cents=row.cost_cents,
        latency_ms=row.latency_ms,
        created_at=created,
        signed_url=make_signed_url(row.id),
        slide_index=row.slide_index,
    )


def _friendly_provider_error(e: Exception) -> str:
    msg = str(e).lower()
    if "rate" in msg or "429" in msg:
        return "The image provider rate-limited us. Wait 30 seconds and try again."
    if "billing" in msg or "quota" in msg or "insufficient" in msg:
        return (
            "The image provider's billing/quota is exhausted. Check your OpenAI "
            "dashboard — add billing or wait for the monthly reset."
        )
    if "content" in msg and ("policy" in msg or "filter" in msg):
        return (
            "The image provider's content filter rejected this brief. Try "
            "regenerating — sometimes a phrasing change clears it."
        )
    if "api_key" in msg or "unauthor" in msg or "401" in msg:
        return "OpenAI API key is missing or invalid. Set OPENAI_API_KEY and bounce the API."
    return "The render couldn't complete. Try again — most provider errors are transient."
