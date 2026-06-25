"""Coach API surface. Post W1-12: brand-scoped reads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.cache.redis_cache import cache_get, cache_set
from aicmo.db.session import get_db
from aicmo.modules.coach.analytics_summary import build_analytics_summary
from aicmo.modules.coach.reality import evaluate_goal
from aicmo.modules.coach.schemas import (
    AnalyticsSummary,
    RealityCheck,
    RealityCheckRequest,
    WeeklyPlan,
)
from aicmo.modules.coach.weekly import build_weekly_plan
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/coach", tags=["coach"])


async def _require_profile(
    session: AsyncSession, brand_id: uuid.UUID
) -> BusinessProfileResponse:
    row = await onboarding_service.get_profile_or_none(session, brand_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before using the AI coach",
        )
    return BusinessProfileResponse.model_validate(row)


@router.post("/reality-check", response_model=RealityCheck)
async def post_reality_check(
    payload: RealityCheckRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> RealityCheck:
    profile = await _require_profile(session, tenant.brand_id)
    return await evaluate_goal(
        profile=profile,
        goal_text=payload.goal_text,
        timeline_hint=payload.timeline_hint,
    )


@router.get("/weekly", response_model=WeeklyPlan)
async def get_weekly_plan(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> WeeklyPlan:
    cache_key = f"coach:weekly:{tenant.brand_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return WeeklyPlan.model_validate(cached)

    profile = await _require_profile(session, tenant.brand_id)
    plan = await build_weekly_plan(session, profile=profile)
    await cache_set(cache_key, plan.model_dump(mode="json"), ttl_seconds=43_200)
    return plan


@router.get("/analytics-summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AnalyticsSummary:
    profile = await _require_profile(session, tenant.brand_id)
    return await build_analytics_summary(session, profile=profile)
