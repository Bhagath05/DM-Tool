from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.ads import service
from aicmo.modules.ads.schemas import (
    GenerateAdRequest,
    GeneratedAdList,
    GeneratedAdResponse,
    UpdateAdRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/ads", tags=["ads"])


@router.post(
    "/generate",
    response_model=GeneratedAdResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_ad(
    payload: GenerateAdRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> GeneratedAdResponse:
    return await service.generate(session, tenant=tenant, payload=payload)


@router.get("", response_model=GeneratedAdList)
async def list_ads(
    saved_only: bool = Query(default=False),
    ad_type: str | None = Query(default=None),
    objective: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedAdList:
    items = await service.list_ads(
        session,
        tenant=tenant,
        saved_only=saved_only,
        ad_type=ad_type,
        objective=objective,
        limit=limit,
    )
    return GeneratedAdList(items=items)


@router.get("/{ad_id}", response_model=GeneratedAdResponse)
async def get_ad(
    ad_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GeneratedAdResponse:
    return await service.get_one(session, tenant=tenant, ad_id=ad_id)


@router.patch("/{ad_id}", response_model=GeneratedAdResponse)
async def update_ad(
    ad_id: uuid.UUID,
    payload: UpdateAdRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.edit")),
) -> GeneratedAdResponse:
    return await service.set_saved(
        session,
        tenant=tenant,
        ad_id=ad_id,
        is_saved=payload.is_saved,
    )


@router.delete("/{ad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ad(
    ad_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> None:
    await service.delete_ad(session, tenant=tenant, ad_id=ad_id)
