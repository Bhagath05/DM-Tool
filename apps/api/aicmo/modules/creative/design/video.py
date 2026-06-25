"""CS6 video orchestration — render a reel design, read status, prepare exports.

The design stays the source of truth; this kicks off the async render (Arq)
and reads back the produced MP4 + captions as OUTPUTS. Reuses the existing
metering, cost-abuse gates, and storage from CV0.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative import cost as cost_ledger
from aicmo.modules.creative import metering
from aicmo.modules.creative.models import CreativeAsset, CreativeExport, CreativeProject
from aicmo.modules.creative.storage.base import StorageRef
from aicmo.modules.creative.storage.registry import get_storage_backend
from aicmo.modules.video.bridge import bridge_design_to_project
from aicmo.tenancy.context import TenantContext

# Publishing targets → (format slug, width, height). All vertical 9:16 except
# LinkedIn (square performs best in-feed).
_PLATFORM_FORMAT: dict[str, tuple[str, int, int]] = {
    "instagram_reels": ("instagram_reels", 1080, 1920),
    "tiktok": ("tiktok", 1080, 1920),
    "youtube_shorts": ("youtube_shorts", 1080, 1920),
    "facebook_reels": ("facebook_ads", 1080, 1920),
    "linkedin": ("linkedin_video", 1080, 1080),
}


class OverDailyCap(Exception):
    def __init__(self, cap: int) -> None:
        self.cap = cap


class OverBudget(Exception):
    pass


async def start_render(session: AsyncSession, *, tenant: TenantContext, design) -> CreativeProject:
    """Bridge the design → project + scenes, run the cost/quota gates, and mark
    it ready to enqueue. Raises OverDailyCap / OverBudget when a hard cap trips."""
    project = await bridge_design_to_project(session, tenant=tenant, design=design)

    # Soft plan-quota gate (won't block unless billing enforcement is on).
    await metering.enforce_video_quota(session, organization_id=tenant.organization_id)
    # Hard cost-abuse gates (always on).
    cap = await metering.check_daily_cap(
        session, organization_id=tenant.organization_id, user_uuid=tenant.user_uuid
    )
    if cap.over:
        raise OverDailyCap(cap.cap)
    if await cost_ledger.org_budget_exceeded(
        session, organization_id=tenant.organization_id, add_cents=project.estimated_cost_cents
    ):
        project.status = "blocked_budget"
        raise OverBudget()

    project.status = "scripting"
    return project


async def get_video_status(session: AsyncSession, *, tenant: TenantContext, design) -> dict:
    """Latest render status + signed URLs for a design's video output."""
    if design.creative_project_id is None:
        return {"status": "none"}
    project = await session.get(CreativeProject, design.creative_project_id)
    if project is None or project.brand_id != tenant.brand_id:
        return {"status": "none"}
    asset = await session.scalar(
        select(CreativeAsset)
        .where(CreativeAsset.creative_project_id == project.id, CreativeAsset.media_type == "video")
        .order_by(CreativeAsset.created_at.desc())
    )
    video_url = captions_url = None
    asset_id = duration_ms = None
    if asset is not None:
        asset_id = asset.id
        duration_ms = asset.duration_ms
        backend = get_storage_backend()
        if asset.storage_key:
            video_url = backend.signed_url(StorageRef(backend=asset.storage_backend, key=asset.storage_key))
        if asset.caption_storage_key:
            captions_url = backend.signed_url(
                StorageRef(backend=asset.storage_backend, key=asset.caption_storage_key)
            )
    return {
        "project": project, "asset_id": asset_id, "video_url": video_url,
        "captions_url": captions_url, "duration_ms": duration_ms,
        "scenes": (project.spec or {}).get("scenes"),
    }


async def prepare_exports(
    session: AsyncSession, *, tenant: TenantContext, asset_id: uuid.UUID, platforms: list[str]
) -> list[CreativeExport] | None:
    """Prepare per-platform exports of the SAME MP4 (re-target metadata; the
    rendered file is reused, not re-encoded in CS6)."""
    asset = await session.scalar(
        select(CreativeAsset).where(
            CreativeAsset.id == asset_id, CreativeAsset.brand_id == tenant.brand_id
        )
    )
    if asset is None:
        return None
    out: list[CreativeExport] = []
    for p in platforms:
        slug, w, h = _PLATFORM_FORMAT[p]
        ex = CreativeExport(
            organization_id=tenant.organization_id, brand_id=tenant.brand_id,
            creative_asset_id=asset.id, target_platform=p, format_slug=slug,
            storage_backend=asset.storage_backend, storage_key=asset.storage_key,
            width=w, height=h, status="ready",
        )
        session.add(ex)
        out.append(ex)
    await session.flush()
    return out


async def list_exports(
    session: AsyncSession, *, tenant: TenantContext, asset_id: uuid.UUID
) -> list[CreativeExport]:
    rows = await session.execute(
        select(CreativeExport)
        .where(CreativeExport.creative_asset_id == asset_id)
        .order_by(CreativeExport.created_at.desc())
    )
    return list(rows.scalars().all())
