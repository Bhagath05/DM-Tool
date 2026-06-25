from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends import service
from aicmo.modules.trends.analyzer import run_refresh
from aicmo.modules.trends.schemas import TrendReportResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/report", response_model=TrendReportResponse)
async def get_report(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> TrendReportResponse:
    report = await service.require_report(session, tenant.brand_id)
    return service._to_response(report)  # noqa: SLF001


@router.post("/refresh", response_model=TrendReportResponse)
async def refresh(
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> TrendReportResponse:
    profile = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before refreshing trends",
        )

    response, started = await service.start_refresh(session, tenant=tenant)
    if started:
        snapshot = BusinessProfileResponse.model_validate(profile)
        background.add_task(run_refresh, str(response.id), snapshot)
    return response
