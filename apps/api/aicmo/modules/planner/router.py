"""Planner HTTP surface.

  GET /planner/today — today's grounded task plan (plans only; nothing runs).

Tenant-scoped, gated on analytics.view (a read-style daily surface like the
Today view / Opportunities). One LLM call per request; the frontend caches.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.planner import service
from aicmo.modules.planner.schemas import DailyPlanResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/planner", tags=["planner"])


@router.get("/today", response_model=DailyPlanResponse)
async def get_today(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> DailyPlanResponse:
    try:
        return await service.plan_today(session, brand_id=tenant.brand_id)
    except service.ProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete your business profile before planning your day.",
        ) from None
