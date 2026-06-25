from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.onboarding import service
from aicmo.modules.onboarding.analyzer import run_analysis
from aicmo.modules.onboarding.schemas import (
    BusinessProfileCreate,
    BusinessProfileResponse,
    BusinessProfileUpdate,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

router = APIRouter(prefix="/business", tags=["business"])


@router.post(
    "/onboarding",
    response_model=BusinessProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_onboarding(
    payload: BusinessProfileCreate,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> BusinessProfileResponse:
    response, _created = await service.create_or_replace_profile(
        session, tenant=tenant, payload=payload
    )
    background.add_task(run_analysis, str(response.id), response)
    return response


@router.get("/profile", response_model=BusinessProfileResponse)
async def get_profile(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> BusinessProfileResponse:
    profile = await service.require_profile(session, tenant.brand_id)
    return service._to_response(profile)  # noqa: SLF001


@router.put("/profile", response_model=BusinessProfileResponse)
async def update_profile(
    payload: BusinessProfileUpdate,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> BusinessProfileResponse:
    response, reanalyze = await service.update_profile(
        session, tenant=tenant, payload=payload
    )
    if reanalyze:
        background.add_task(run_analysis, str(response.id), response)
    return response


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> None:
    await service.delete_profile(session, tenant=tenant)


@router.post("/profile/retry-analysis", response_model=BusinessProfileResponse)
async def retry_analysis(
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> BusinessProfileResponse:
    """Re-run the AI analysis on the existing profile without re-onboarding.

    Used when the first analysis hit a transient provider error (e.g. Gemini
    503). Resets the row to `pending`, schedules a fresh `run_analysis`
    background task, and returns the new pending state so the dashboard
    polling picks it up.
    """
    response = await service.reset_analysis_for_retry(session, tenant=tenant)
    background.add_task(run_analysis, str(response.id), response)
    return response
