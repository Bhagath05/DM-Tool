from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.content import service
from aicmo.modules.content.schemas import (
    GeneratedContentList,
    GeneratedContentResponse,
    GenerateRequest,
    UpdateRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/content", tags=["content"])


@router.post(
    "/generate",
    response_model=GeneratedContentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_content(
    payload: GenerateRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> GeneratedContentResponse:
    return await service.generate(session, tenant=tenant, payload=payload)


@router.get("", response_model=GeneratedContentList)
async def list_content(
    saved_only: bool = Query(default=False),
    content_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedContentList:
    items = await service.list_content(
        session,
        tenant=tenant,
        saved_only=saved_only,
        content_type=content_type,
        limit=limit,
    )
    return GeneratedContentList(items=items)


@router.get("/{content_id}", response_model=GeneratedContentResponse)
async def get_content(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedContentResponse:
    return await service.get_one(
        session, tenant=tenant, content_id=content_id
    )


@router.patch("/{content_id}", response_model=GeneratedContentResponse)
async def update_content(
    content_id: uuid.UUID,
    payload: UpdateRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.edit")),
) -> GeneratedContentResponse:
    return await service.set_saved(
        session,
        tenant=tenant,
        content_id=content_id,
        is_saved=payload.is_saved,
    )


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> None:
    await service.delete_content(
        session, tenant=tenant, content_id=content_id
    )
