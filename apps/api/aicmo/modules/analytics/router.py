from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.analytics import service
from aicmo.modules.analytics.schemas import (
    LandingPagePerformanceResponse,
    OverviewKpis,
    SourcesResponse,
    StatusDistribution,
    TimelineResponse,
    TopAssetsResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewKpis)
async def get_overview(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> OverviewKpis:
    return await service.overview(session, brand_id=tenant.brand_id)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> TimelineResponse:
    return await service.timeline(
        session, brand_id=tenant.brand_id, window_days=window_days
    )


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> SourcesResponse:
    return await service.by_source(session, brand_id=tenant.brand_id, limit=limit)


@router.get("/landing-pages", response_model=LandingPagePerformanceResponse)
async def get_landing_page_performance(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> LandingPagePerformanceResponse:
    return await service.landing_page_performance(session, brand_id=tenant.brand_id)


@router.get("/status-distribution", response_model=StatusDistribution)
async def get_status_distribution(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> StatusDistribution:
    return await service.status_distribution(session, brand_id=tenant.brand_id)


@router.get("/top-assets", response_model=TopAssetsResponse)
async def get_top_assets(
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> TopAssetsResponse:
    return await service.top_assets(session, brand_id=tenant.brand_id, limit=limit)
