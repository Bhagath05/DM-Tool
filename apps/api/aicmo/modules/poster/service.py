"""Orchestrate a LinkedIn poster: copy + art direction → meaningful hero
image → theme → render chosen layout → store → signed URL.
"""

from __future__ import annotations

import asyncio
import base64
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative.storage.registry import get_storage_backend
from aicmo.modules.poster import copy as copy_mod
from aicmo.modules.poster import theme as theme_mod
from aicmo.modules.poster.copy import clamp
from aicmo.modules.poster.media import sign_storage_key
from aicmo.modules.poster.render import (
    PosterRenderUnavailable,
    render_poster,
    renderer_available,
)
from aicmo.modules.poster.schemas import (
    LinkedInComposeRequest,
    LinkedInComposeResult,
    LinkedInCopy,
)

log = structlog.get_logger()

_W = _H = 1200
_SCALE = 2


async def _gather_brand(
    session: AsyncSession, organization_id: uuid.UUID, brand_id: uuid.UUID | None
) -> tuple[str, str | None, str | None]:
    """(brand_name, website, business_context). Defensive — any missing piece
    falls back to a neutral default so the poster still renders."""
    brand_name: str | None = None
    website: str | None = None
    context: str | None = None
    try:
        from aicmo.modules.brands.models import Brand
        from aicmo.modules.orgs.models import Organization

        if brand_id:
            brand_name = (
                await session.execute(select(Brand.name).where(Brand.id == brand_id))
            ).scalar_one_or_none()
        org = (
            await session.execute(
                select(Organization.name, Organization.website).where(
                    Organization.id == organization_id
                )
            )
        ).first()
        if org:
            brand_name = brand_name or org[0]
            website = org[1]
    except Exception as exc:  # noqa: BLE001
        log.warning("poster.brand.partial", error=str(exc)[:120])

    try:
        from aicmo.modules.onboarding.models import BusinessProfile

        bp = (
            await session.execute(
                select(BusinessProfile)
                .where(BusinessProfile.organization_id == organization_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if bp is not None:
            website = website or getattr(bp, "website", None)
            bits = [
                f"Industry: {bp.industry}" if getattr(bp, "industry", None) else None,
                f"Audience: {bp.target_audience}" if getattr(bp, "target_audience", None) else None,
                f"Brand tone: {bp.brand_tone}" if getattr(bp, "brand_tone", None) else None,
                f"Goal: {bp.primary_goal_text}" if getattr(bp, "primary_goal_text", None) else None,
            ]
            context = " | ".join([b for b in bits if b]) or None
    except Exception as exc:  # noqa: BLE001
        log.warning("poster.profile.partial", error=str(exc)[:120])

    return brand_name or "Your Brand", website, context


def _image_prompt(copy: LinkedInCopy) -> str:
    if copy.image_style == "illustration":
        style = (
            "clean modern vector illustration, flat editorial style, crisp shapes, "
            "professional, generous negative space"
        )
    else:
        style = (
            "ultra-realistic professional advertising photograph, sharp focus, "
            "natural cinematic lighting, shallow depth of field"
        )
    return (
        f"{copy.image_concept}. {style}. Square 1:1 composition, premium quality. "
        "Absolutely NO text, NO words, NO letters, NO numbers, NO logos, NO watermark, NO UI."
    )


async def _generate_hero(copy: LinkedInCopy) -> str | None:
    """Generate the business-meaningful hero image → data URI. None on any failure."""
    try:
        from aicmo.providers.images.base import ImageRenderRequest
        from aicmo.providers.images.registry import get_image_provider

        provider = get_image_provider("openai")
        async with asyncio.timeout(90):
            res = await provider.render(
                ImageRenderRequest(
                    prompt=_image_prompt(copy),
                    size="1024x1024",
                    negative_prompt="text, words, letters, numbers, watermark, logo, ui, frame, border",
                )
            )
        b64 = base64.b64encode(res.image_bytes).decode()
        log.info("poster.hero.ok", style=copy.image_style, concept=copy.image_concept[:60])
        return f"data:image/png;base64,{b64}"
    except Exception as exc:  # noqa: BLE001
        log.warning("poster.hero.skip", error=str(exc)[:160])
        return None


async def _render_and_store(
    *, organization_id: uuid.UUID, copy: LinkedInCopy, theme, generate_image: bool
) -> LinkedInComposeResult:
    if not renderer_available():
        raise PosterRenderUnavailable(
            "No HTML renderer available — install Playwright or set POSTER_CHROME_BIN."
        )
    hero = await _generate_hero(copy) if generate_image else None
    png = await asyncio.to_thread(
        render_poster, copy, theme, hero_data_uri=hero, width=_W, height=_H, scale=_SCALE
    )
    storage = get_storage_backend()
    key = f"{organization_id}/poster/{uuid.uuid4().hex}.png"
    ref = storage.put(key=key, data=png, content_type="image/png")
    log.info(
        "poster.stored", org=str(organization_id), key=ref.key,
        bytes=len(png), layout=copy.layout, used_ai_image=bool(hero),
    )
    return LinkedInComposeResult(
        image_url=sign_storage_key(ref.key),
        width=_W,
        height=_H,
        post_body=copy.post_body,
        hashtags=copy.hashtags,
        fields=copy,
        rendered_id=ref.key,
        used_ai_image=bool(hero),
    )


async def compose_linkedin(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    req: LinkedInComposeRequest,
) -> LinkedInComposeResult:
    """Topic → branded, business-meaningful poster + LinkedIn caption."""
    brand_name, website, context = await _gather_brand(session, organization_id, brand_id)
    copy, used_llm = await copy_mod.compose(
        req.topic, goal=req.goal, brand_name=brand_name, context=context
    )
    theme = theme_mod.build_theme(palette=copy.palette, brand_name=brand_name, website=website)
    log.info(
        "poster.compose", org=str(organization_id), used_llm=used_llm,
        layout=copy.layout, palette=copy.palette, topic=req.topic[:80],
    )
    return await _render_and_store(
        organization_id=organization_id, copy=copy, theme=theme,
        generate_image=req.generate_image,
    )


async def rerender_linkedin(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    fields: LinkedInCopy,
    generate_image: bool = True,
) -> LinkedInComposeResult:
    """Re-render user-edited copy (no caption LLM). Regenerates the hero image
    from the (possibly edited) image_concept when generate_image is true."""
    brand_name, website, _ = await _gather_brand(session, organization_id, brand_id)
    fields = clamp(fields)
    theme = theme_mod.build_theme(palette=fields.palette, brand_name=brand_name, website=website)
    return await _render_and_store(
        organization_id=organization_id, copy=fields, theme=theme,
        generate_image=generate_image,
    )
