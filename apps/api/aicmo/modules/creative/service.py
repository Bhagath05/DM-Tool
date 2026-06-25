"""Creative project service — CRUD + state machine (Creative Core V0).

Media-agnostic core. V0 only accepts `media_type=video` (other creative
types are reserved enum values that future generators will fill). No
provider calls here — the pipeline jobs do the work; this owns the
project row + state transitions + the pre-flight estimate.
"""

from __future__ import annotations

import math
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative import formats
from aicmo.modules.creative.models import CreativeProject
from aicmo.modules.creative.schemas import CreateProjectRequest
from aicmo.modules.video.providers.registry import get_video_provider
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

_VIDEO_CLIP_SECONDS = 8  # Veo clip ceiling → scene count


async def estimate_project_cost_cents(
    *, max_duration_s: int | None, width: int, height: int
) -> tuple[int, int]:
    """Return (estimated_cost_cents, scene_count) using the active provider's
    estimator. Pre-flight gate input — shown before the founder confirms."""
    provider = get_video_provider()
    duration = max_duration_s or _VIDEO_CLIP_SECONDS
    scenes = max(1, math.ceil(duration / _VIDEO_CLIP_SECONDS))
    per_clip = provider.estimate_cost(
        duration_s=_VIDEO_CLIP_SECONDS, width=width, height=height
    )
    return per_clip * scenes, scenes


async def create_project(
    session: AsyncSession, *, tenant: TenantContext, payload: CreateProjectRequest
) -> CreativeProject:
    fmt = await formats.get_format(session, payload.format_slug)
    if fmt is None or not fmt.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown format: {payload.format_slug}")
    # V0 supports only the video subsystem.
    if fmt.media_type != "video":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Creative Core V0 supports video formats only (got {fmt.media_type}).",
        )

    est_cents, _scenes = await estimate_project_cost_cents(
        max_duration_s=fmt.max_duration_s, width=fmt.width, height=fmt.height
    )

    project = CreativeProject(
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        campaign_id=payload.campaign_id,
        title=payload.title.strip(),
        brief=payload.sanitized_brief(),
        creative_type="video",
        media_type="video",
        format_slug=fmt.slug,
        platform=fmt.platform,
        objective=payload.objective,
        goal=payload.goal,
        tone=payload.tone,
        audio_mode=payload.audio_mode,
        status="draft",
        spec={
            "aspect_ratio": fmt.aspect_ratio,
            "width": fmt.width,
            "height": fmt.height,
            "max_duration_s": fmt.max_duration_s,
            "fps": fmt.fps,
            "style_preset": fmt.style_preset,
        },
        estimated_cost_cents=est_cents,
        actual_cost_cents=0,
    )
    session.add(project)
    await session.flush()
    return project


async def get_project(
    session: AsyncSession, *, tenant: TenantContext, project_id: uuid.UUID
) -> CreativeProject:
    row = (
        await session.execute(
            select(CreativeProject).where(
                CreativeProject.id == project_id,
                CreativeProject.brand_id == tenant.brand_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return row


async def list_projects(
    session: AsyncSession, *, tenant: TenantContext, limit: int = 20
) -> list[CreativeProject]:
    limit = max(1, min(limit, 100))
    stmt = (
        select(CreativeProject)
        .where(CreativeProject.brand_id == tenant.brand_id)
        .order_by(desc(CreativeProject.created_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def set_status(
    session: AsyncSession, *, project: CreativeProject, new_status: str
) -> None:
    project.status = new_status
    await session.flush()


async def cancel_project(
    session: AsyncSession, *, tenant: TenantContext, project_id: uuid.UUID
) -> CreativeProject:
    project = await get_project(session, tenant=tenant, project_id=project_id)
    if project.status in ("ready", "published", "canceled"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Cannot cancel a {project.status} project"
        )
    project.status = "canceled"
    await session.flush()
    return project
