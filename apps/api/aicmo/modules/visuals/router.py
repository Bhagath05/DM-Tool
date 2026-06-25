from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.visuals import render as render_service
from aicmo.modules.visuals import service
from aicmo.modules.visuals.render_schemas import (
    RenderedVisualList,
    RenderedVisualResponse,
    RenderQuotaStatus,
    RenderRequest,
)
from aicmo.modules.visuals.schemas import (
    GenerateVisualRequest,
    GeneratedVisualList,
    GeneratedVisualResponse,
    UpdateVisualRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/visuals", tags=["visuals"])


@router.post(
    "/generate",
    response_model=GeneratedVisualResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_visual(
    payload: GenerateVisualRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> GeneratedVisualResponse:
    return await service.generate(session, tenant=tenant, payload=payload)


@router.get("", response_model=GeneratedVisualList)
async def list_visuals(
    saved_only: bool = Query(default=False),
    visual_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedVisualList:
    items = await service.list_visuals(
        session,
        tenant=tenant,
        saved_only=saved_only,
        visual_type=visual_type,
        limit=limit,
    )
    return GeneratedVisualList(items=items)


# IMPORTANT: declare /render-quota BEFORE /{visual_id} or FastAPI matches
# the UUID-parameterised route first and 422s on "render-quota".
@router.get("/render-quota", response_model=RenderQuotaStatus)
async def get_render_quota(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> RenderQuotaStatus:
    return await render_service.get_quota(session, brand_id=tenant.brand_id)


@router.get("/{visual_id}", response_model=GeneratedVisualResponse)
async def get_visual(
    visual_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedVisualResponse:
    return await service.get_one(session, tenant=tenant, visual_id=visual_id)


@router.patch("/{visual_id}", response_model=GeneratedVisualResponse)
async def update_visual(
    visual_id: uuid.UUID,
    payload: UpdateVisualRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.edit")),
) -> GeneratedVisualResponse:
    return await service.set_saved(
        session,
        tenant=tenant,
        visual_id=visual_id,
        is_saved=payload.is_saved,
    )


@router.delete("/{visual_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visual(
    visual_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> None:
    await service.delete_visual(session, tenant=tenant, visual_id=visual_id)


# ---------- Phase 4-A: render endpoints ----------


@router.post(
    "/{visual_id}/render",
    response_model=RenderedVisualResponse,
    status_code=status.HTTP_201_CREATED,
)
async def render_visual_endpoint(
    visual_id: uuid.UUID,
    payload: RenderRequest = RenderRequest(),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> RenderedVisualResponse:
    return await render_service.render_visual(
        session,
        tenant=tenant,
        visual_id=visual_id,
        quality=payload.quality,
    )


@router.get("/{visual_id}/renders", response_model=RenderedVisualList)
async def list_renders(
    visual_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> RenderedVisualList:
    items = await render_service.list_renders(
        session, tenant=tenant, visual_id=visual_id
    )
    return RenderedVisualList(items=items)
