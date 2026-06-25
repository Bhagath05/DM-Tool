"""Design → Video bridge (CS6).

A reel/video `creative_design` (the editable source of truth) is the input;
this derives a `creative_project` + `video_scene` rows from its scene pages so
the existing video pipeline can render it. The design is never consumed or
mutated (only linked via `creative_project_id`) — the MP4 is an OUTPUT of the
design, exactly per the Creative Studio contract.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative import formats
from aicmo.modules.creative.models import CreativeProject
from aicmo.modules.video.models import VideoScene
from aicmo.tenancy.context import TenantContext

# Design aspect → a seeded video format (migration 0034).
_ASPECT_FORMAT: dict[str, str] = {
    "9:16": "instagram_reels",
    "16:9": "product_commercial",
    "1:1": "facebook_ads",
    "4:5": "meta_ads",
}


def scenes_from_design(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """One scene per design page. Pulls headline (visual prompt), subtitle/body
    (voiceover), and cta from the layer roles."""
    scenes: list[dict[str, Any]] = []
    for i, page in enumerate(doc.get("pages", [])):
        layers = page.get("layers", [])

        def role(r: str) -> str | None:
            return next((l.get("text") for l in layers if l.get("role") == r and l.get("text")), None)

        headline = role("headline") or ""
        sub = role("subtitle") or role("body") or ""
        cta = role("cta") or ""
        dur = (page.get("duration_ms") or 2500) / 1000.0
        prompt = " — ".join([x for x in (headline, sub) if x]) or "cinematic scene"
        scenes.append({
            "index": i,
            "prompt": prompt[:2000],
            "duration_s": min(max(dur, 1.0), 8.0),  # Veo caps single clips ~8s
            "vo": (sub or headline)[:500],
            "cta": cta,
        })
    return scenes


async def bridge_design_to_project(
    session: AsyncSession, *, tenant: TenantContext, design
) -> CreativeProject:
    """Create the video project + scenes for a reel design and link it back."""
    doc = design.doc or {}
    aspect = doc.get("aspect") or "9:16"
    slug = _ASPECT_FORMAT.get(aspect, "instagram_reels")
    fmt = await formats.get_format(session, slug)
    width = fmt.width if fmt else 1080
    height = fmt.height if fmt else 1920
    fps = fmt.fps if fmt else 24
    max_dur = fmt.max_duration_s if fmt else 60

    scenes = scenes_from_design(doc)
    brief = (" ".join(s["prompt"] for s in scenes)[:2000]) or design.name

    project = CreativeProject(
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        title=design.name,
        brief=brief,
        creative_type="video",
        media_type="video",
        format_slug=slug if fmt else None,
        platform=fmt.platform if fmt else None,
        objective="reel",
        goal=design.name,
        audio_mode="tts_voiceover",
        status="draft",
        spec={
            "aspect_ratio": aspect, "width": width, "height": height,
            "max_duration_s": max_dur, "fps": fps,
            "design_id": str(design.id), "scenes": len(scenes),
        },
        estimated_cost_cents=0,
        actual_cost_cents=0,
    )
    session.add(project)
    await session.flush()  # populate project.id

    for s in scenes:
        session.add(VideoScene(
            organization_id=tenant.organization_id, brand_id=tenant.brand_id,
            creative_project_id=project.id, scene_index=s["index"], prompt=s["prompt"],
            duration_s=Decimal(str(round(s["duration_s"], 1))), vo_line=s["vo"], status="pending",
        ))

    # Link the design → project (a metadata pointer; NOT a doc mutation, so it
    # never needs a revision — the editable doc is unchanged).
    design.creative_project_id = project.id
    await session.flush()
    return project
