"""Marketing-analytics API.

Read-only, tenant-scoped platform analytics + the Performance Marketer. Every
route is gated on ``analytics.view`` and scoped to ``tenant.brand_id`` — one
tenant can never read another's metrics. Nothing here publishes, spends, or
mutates a connected account (autonomy-safe: advisory only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.marketing_analytics import content as content_analytics
from aicmo.modules.marketing_analytics import service
from aicmo.modules.marketing_analytics.schemas import (
    ContentPerformanceReport,
    InsightsResponse,
    PerformanceMarketerReport,
    PlatformsResponse,
    TrendsResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/marketing-analytics", tags=["marketing-analytics"])


@router.get("/platforms", response_model=PlatformsResponse)
async def get_platforms(
    window_days: int = Query(default=7, ge=1, le=90),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> PlatformsResponse:
    return await service.get_platforms(session, brand_id=tenant.brand_id, window_days=window_days)


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    window_days: int = Query(default=7, ge=1, le=90),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> TrendsResponse:
    return await service.get_trends(
        session,
        brand_id=tenant.brand_id,
        window_days=window_days,
        granularity=granularity,
    )


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    window_days: int = Query(default=7, ge=1, le=90),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> InsightsResponse:
    return await service.get_insights(session, brand_id=tenant.brand_id, window_days=window_days)


@router.get("/content", response_model=ContentPerformanceReport)
async def get_content(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> ContentPerformanceReport:
    """Per-content performance: top/worst posts, format comparison, and
    evidence-backed 'repeat this' recommendations. Read-only, tenant-scoped."""
    return await content_analytics.content_report(session, brand_id=tenant.brand_id)


@router.get("/performance", response_model=PerformanceMarketerReport)
async def get_performance(
    window_days: int = Query(default=7, ge=1, le=90),
    narrate: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> PerformanceMarketerReport:
    return await service.performance_report(
        session,
        brand_id=tenant.brand_id,
        window_days=window_days,
        narrate=narrate,
    )
