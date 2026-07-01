"""Marketing Strategist HTTP surface.

  POST /strategist/generate  — kick off strategy generation (async); returns a
                               pending record. content.create (costs an LLM call).
  GET  /strategist/latest    — the current strategy. analytics.view.
  GET  /strategist           — strategy history. analytics.view.

All tenant-scoped via require_permission; every query filters by brand_id.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.strategist import service
from aicmo.modules.strategist.schemas import (
    MarketingStrategyList,
    MarketingStrategyResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/strategist", tags=["strategist"])


@router.post(
    "/generate",
    response_model=MarketingStrategyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> MarketingStrategyResponse:
    profile_row = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete your business profile before generating a strategy.",
        )
    snapshot = BusinessProfileResponse.model_validate(profile_row)
    record = await service.create_pending(session, tenant=tenant)
    # Generate off the request path (big LLM call); the client polls /latest.
    background.add_task(service.run_strategy, str(record.id), snapshot)
    return MarketingStrategyResponse.model_validate(record)


@router.get("/latest", response_model=MarketingStrategyResponse)
async def get_latest(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> MarketingStrategyResponse:
    row = await service.latest(session, brand_id=tenant.brand_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No marketing strategy yet — generate one.",
        )
    return MarketingStrategyResponse.model_validate(row)


@router.get("", response_model=MarketingStrategyList)
async def list_history(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> MarketingStrategyList:
    return await service.list_strategies(session, brand_id=tenant.brand_id)
