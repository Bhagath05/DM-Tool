"""Creative Platform HTTP surface — Creative Core V0.

Flag-gated: when `video_enabled=false` (default), every authoring endpoint
returns 409, so V0 is inert in the running product. The media route is
public (signed-URL verified) like the visuals image route.

V0 only accepts video formats; the unified `/creative/*` surface is ready
for posters/banners/… without new routes.
"""

from __future__ import annotations

from urllib.parse import unquote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.creative import cost as cost_ledger
from aicmo.modules.creative import formats, metering
from aicmo.modules.creative import service as creative_service
from aicmo.modules.creative.schemas import (
    CostBreakdown,
    CostSummary,
    CreateProjectRequest,
    FormatDescriptor,
    ProjectList,
    ProjectResponse,
)
from aicmo.modules.creative.storage.base import StorageRef, verify_key
from aicmo.modules.creative.storage.local import LocalDiskBackend
from aicmo.queue.deps import get_arq_pool
from aicmo.queue.enqueue import enqueue_tenant_job
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

log = structlog.get_logger()

router = APIRouter(prefix="/creative", tags=["creative"])
public_router = APIRouter(prefix="/media", tags=["creative"])

_RequireRead = require_permission("video.read")
_RequireCreate = require_permission("video.create")


def _require_enabled() -> None:
    if not get_settings().video_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Creative video generation isn't enabled yet.",
        )


# ---------------------------------------------------------------------
#  Formats
# ---------------------------------------------------------------------
@router.get("/formats", response_model=list[FormatDescriptor])
async def list_formats(
    _tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> list[FormatDescriptor]:
    _require_enabled()
    rows = await formats.list_formats(session, media_type="video")
    return [FormatDescriptor.model_validate(r) for r in rows]


# ---------------------------------------------------------------------
#  Projects
# ---------------------------------------------------------------------
@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    _require_enabled()
    project = await creative_service.create_project(session, tenant=tenant, payload=payload)
    await session.commit()
    return ProjectResponse.model_validate(project)


@router.get("/projects", response_model=ProjectList)
async def list_projects(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> ProjectList:
    _require_enabled()
    rows = await creative_service.list_projects(session, tenant=tenant)
    return ProjectList(items=[ProjectResponse.model_validate(r) for r in rows])


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    _require_enabled()
    import uuid as _uuid

    project = await creative_service.get_project(
        session, tenant=tenant, project_id=_uuid.UUID(project_id)
    )
    return ProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/start", response_model=ProjectResponse)
async def start_project(
    project_id: str,
    request: Request,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> ProjectResponse:
    _require_enabled()
    import uuid as _uuid

    pid = _uuid.UUID(project_id)
    project = await creative_service.get_project(session, tenant=tenant, project_id=pid)

    # Soft plan-quota gate (won't block unless billing enforcement is on).
    await metering.enforce_video_quota(session, organization_id=tenant.organization_id)

    # Cost-abuse controls (always on — protect against runaway spend).
    cap = await metering.check_daily_cap(
        session, organization_id=tenant.organization_id, user_uuid=tenant.user_uuid
    )
    if cap.over:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily video limit reached ({cap.cap}/day). Try again tomorrow.",
        )
    if await cost_ledger.org_budget_exceeded(
        session, organization_id=tenant.organization_id, add_cents=project.estimated_cost_cents
    ):
        await creative_service.set_status(session, project=project, new_status="blocked_budget")
        await session.commit()
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="This would exceed your monthly creative budget.",
        )

    await creative_service.set_status(session, project=project, new_status="scripting")
    await session.commit()
    await enqueue_tenant_job(pool, "generate_video_stub", str(pid), tenant=tenant)
    return ProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/cancel", response_model=ProjectResponse)
async def cancel_project(
    project_id: str,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    _require_enabled()
    import uuid as _uuid

    project = await creative_service.cancel_project(
        session, tenant=tenant, project_id=_uuid.UUID(project_id)
    )
    await session.commit()
    return ProjectResponse.model_validate(project)


@router.get("/projects/{project_id}/cost", response_model=CostSummary)
async def project_cost(
    project_id: str,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> CostSummary:
    _require_enabled()
    import uuid as _uuid
    from sqlalchemy import select

    from aicmo.modules.creative.models import CreativeCostEvent

    pid = _uuid.UUID(project_id)
    project = await creative_service.get_project(session, tenant=tenant, project_id=pid)
    rows = (
        await session.execute(
            select(CreativeCostEvent.stage, CreativeCostEvent.provider, CreativeCostEvent.cost_cents)
            .where(CreativeCostEvent.creative_project_id == pid)
        )
    ).all()
    return CostSummary(
        project_id=pid,
        estimated_cost_cents=project.estimated_cost_cents,
        actual_cost_cents=project.actual_cost_cents,
        breakdown=[CostBreakdown(stage=s, provider=p, cost_cents=int(c)) for s, p, c in rows],
    )


# ---------------------------------------------------------------------
#  Media serving (public, signed) — LocalDiskBackend only. S3 returns a
#  presigned URL directly (no app round-trip).
# ---------------------------------------------------------------------
@public_router.get("/creative")
async def serve_creative_media(
    key: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
):
    decoded = unquote(key)
    ok, reason = verify_key(decoded, exp, sig)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=reason)
    backend = LocalDiskBackend()
    path = backend.local_path(StorageRef(backend="local", key=decoded))
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return FileResponse(path)
