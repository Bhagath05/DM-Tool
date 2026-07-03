"""Publishing pipeline HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.publishing import assets as asset_registry
from aicmo.modules.publishing import queue_service, service
from aicmo.modules.publishing.models import ContentAsset
from aicmo.modules.publishing.schemas import (
    ApprovalDecisionRequest,
    AssetPerformanceResponse,
    BulkScheduleRequest,
    ContentAssetResponse,
    PublishEventList,
    QueueAnalyticsResponse,
    RescheduleRequest,
    ScheduledPostList,
    ScheduledPostResponse,
    ScheduleFromRecommendationRequest,
    SchedulePostRequest,
)
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


@router.post("/posts/{scheduled_post_id}/retry", response_model=ScheduledPostResponse)
async def retry_post(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostResponse:
    """Operator retry of a failed post — resets the attempt budget + re-publishes."""
    return await service.retry_post(
        session, scheduled_post_id=scheduled_post_id, tenant=tenant
    )


@router.get("/posts/{scheduled_post_id}/events", response_model=PublishEventList)
async def list_post_events(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> PublishEventList:
    """Audit trail (scheduled / attempts / published / failed) for one post."""
    return await service.list_events(
        session, brand_id=tenant.brand_id, scheduled_post_id=scheduled_post_id
    )


# ---------------------------------------------------------------------
#  Phase 6.4 — enterprise queue ops (literal /analytics + /schedule/bulk
#  register fine alongside the existing /posts/{id}/… param routes).
# ---------------------------------------------------------------------
_WRITE = require_permission("content.create")
_VIEW = require_permission("analytics.view")


@router.get("/analytics", response_model=QueueAnalyticsResponse)
async def queue_analytics(
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> QueueAnalyticsResponse:
    return await queue_service.queue_analytics(session, tenant=tenant)


@router.post("/schedule/bulk", response_model=list[ScheduledPostResponse], status_code=201)
async def bulk_schedule(
    payload: BulkScheduleRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> list[ScheduledPostResponse]:
    return await queue_service.bulk_schedule(session, tenant=tenant, payload=payload)


@router.post("/posts/{scheduled_post_id}/cancel", response_model=ScheduledPostResponse)
async def cancel_post(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> ScheduledPostResponse:
    return await queue_service.cancel_post(session, tenant=tenant, post_id=scheduled_post_id)


@router.post("/posts/{scheduled_post_id}/pause", response_model=ScheduledPostResponse)
async def pause_post(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> ScheduledPostResponse:
    return await queue_service.pause_post(session, tenant=tenant, post_id=scheduled_post_id)


@router.post("/posts/{scheduled_post_id}/resume", response_model=ScheduledPostResponse)
async def resume_post(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> ScheduledPostResponse:
    return await queue_service.resume_post(session, tenant=tenant, post_id=scheduled_post_id)


@router.post("/posts/{scheduled_post_id}/reschedule", response_model=ScheduledPostResponse)
async def reschedule_post(
    scheduled_post_id: uuid.UUID, payload: RescheduleRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> ScheduledPostResponse:
    return await queue_service.reschedule_post(
        session, tenant=tenant, post_id=scheduled_post_id,
        scheduled_at=payload.scheduled_at, schedule_timezone=payload.schedule_timezone,
    )


@router.post("/posts/{scheduled_post_id}/submit", response_model=ScheduledPostResponse)
async def submit_for_approval(
    scheduled_post_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_WRITE),
) -> ScheduledPostResponse:
    return await queue_service.submit_for_approval(
        session, tenant=tenant, post_id=scheduled_post_id
    )


@router.post("/posts/{scheduled_post_id}/approve", response_model=ScheduledPostResponse)
async def approve_post(
    scheduled_post_id: uuid.UUID, payload: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.approve")),
) -> ScheduledPostResponse:
    return await queue_service.approve_post(
        session, tenant=tenant, post_id=scheduled_post_id, reason=payload.reason
    )


@router.post("/posts/{scheduled_post_id}/reject", response_model=ScheduledPostResponse)
async def reject_post(
    scheduled_post_id: uuid.UUID, payload: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.approve")),
) -> ScheduledPostResponse:
    return await queue_service.reject_post(
        session, tenant=tenant, post_id=scheduled_post_id, reason=payload.reason
    )


@router.post("/posts/{scheduled_post_id}/request-changes", response_model=ScheduledPostResponse)
async def request_changes(
    scheduled_post_id: uuid.UUID, payload: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.approve")),
) -> ScheduledPostResponse:
    return await queue_service.request_changes(
        session, tenant=tenant, post_id=scheduled_post_id, reason=payload.reason
    )
