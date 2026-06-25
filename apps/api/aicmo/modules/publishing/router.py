"""Publishing pipeline HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.publishing import service
from aicmo.modules.publishing.schemas import (
    AssetPerformanceResponse,
    ContentAssetResponse,
    ScheduleFromRecommendationRequest,
    SchedulePostRequest,
    ScheduledPostList,
    ScheduledPostResponse,
)
from aicmo.modules.publishing.models import ContentAsset
from aicmo.modules.publishing import assets as asset_registry
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/publishing", tags=["publishing"])


@router.get("/assets", response_model=list[ContentAssetResponse])
async def list_assets(
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> list[ContentAssetResponse]:
    from sqlalchemy import desc, select

    rows = (
        await session.execute(
            select(ContentAsset)
            .where(ContentAsset.brand_id == tenant.brand_id)
            .order_by(desc(ContentAsset.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [ContentAssetResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}", response_model=ContentAssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ContentAssetResponse:
    row = await asset_registry.get_asset(
        session, brand_id=tenant.brand_id, asset_id=asset_id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return ContentAssetResponse.model_validate(row)


@router.get("/assets/{asset_id}/performance", response_model=AssetPerformanceResponse)
async def get_asset_performance(
    asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AssetPerformanceResponse:
    return await service.get_asset_performance(
        session, brand_id=tenant.brand_id, asset_id=asset_id
    )


@router.get("/calendar", response_model=ScheduledPostList)
async def list_calendar(
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostList:
    return await service.list_scheduled(
        session, brand_id=tenant.brand_id, limit=limit
    )


@router.post("/schedule", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED)
async def schedule_post(
    payload: SchedulePostRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostResponse:
    return await service.schedule_post(session, tenant=tenant, payload=payload)


@router.post(
    "/schedule/recommendation",
    response_model=ScheduledPostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_from_recommendation(
    payload: ScheduleFromRecommendationRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostResponse:
    return await service.schedule_from_recommendation(
        session, tenant=tenant, payload=payload
    )


@router.post("/publish/{scheduled_post_id}", response_model=ScheduledPostResponse)
async def publish_now(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostResponse:
    return await service.publish_scheduled_post(
        session, scheduled_post_id=scheduled_post_id, tenant=tenant
    )
