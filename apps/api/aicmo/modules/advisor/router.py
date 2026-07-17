"""Advisor API — memory, intelligence, outcomes, agent."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.cache.redis_cache import cache_get, cache_set
from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.advisor import service
from aicmo.modules.advisor.agent import generate_agent_report
from aicmo.modules.advisor.brain import brain_completeness, load_business_brain
from aicmo.modules.advisor.effectiveness import list_effectiveness
from aicmo.modules.advisor.execute import execute_recommendation
from aicmo.modules.advisor.health import compute_health
from aicmo.modules.advisor.intelligence import compose_intelligence
from aicmo.modules.advisor.readiness import assess_readiness
from aicmo.modules.advisor.schemas import (
    AdvisorHistoryList,
    AdvisorReadinessResponse,
    AdvisorRecommendationResponse,
    AgentReport,
    AgentReportType,
    BusinessBrainResponse,
    BusinessBrainUpdate,
    EffectivenessChannel,
    EffectivenessResponse,
    ExecuteRecommendationRequest,
    ExecuteRecommendationResponse,
    IntelligenceReport,
    MarketingHealthResponse,
    UpdateRecommendationStatusRequest,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse, BusinessProfileUpdate
from aicmo.modules.publishing.schemas import (
    ScheduledPostResponse,
    ScheduleFromRecommendationRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/advisor", tags=["advisor"])


async def _require_profile(
    session: AsyncSession, tenant: TenantContext
) -> BusinessProfileResponse:
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding first",
        )
    return BusinessProfileResponse.model_validate(profile_row)


@router.get("/readiness", response_model=AdvisorReadinessResponse)
async def get_readiness(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AdvisorReadinessResponse:
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        return AdvisorReadinessResponse(
            ready=False,
            message="Complete business onboarding first.",
            suggested_setup_steps=["Complete business onboarding"],
            signal_count=0,
        )
    profile = BusinessProfileResponse.model_validate(profile_row)
    ready, steps, message = await assess_readiness(
        session, profile=profile, signal_count=0
    )
    return AdvisorReadinessResponse(
        ready=ready,
        message=message,
        suggested_setup_steps=steps,
        signal_count=0,
    )


@router.get("/health", response_model=MarketingHealthResponse)
async def get_marketing_health(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> MarketingHealthResponse:
    """Plain-language marketing health for the AI headquarters. Computed
    from this brand's real rows — no LLM call, so it renders instantly and
    can't invent a number."""
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        return MarketingHealthResponse(
            overall=0,
            overall_status="bad",
            headline="Tell us about your business and we'll get started.",
            focus_key="brand",
            scores=[],
        )
    profile = BusinessProfileResponse.model_validate(profile_row)
    return await compute_health(session, profile=profile)


@router.get("/history", response_model=AdvisorHistoryList)
async def get_history(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
    limit: int = Query(default=50, ge=1, le=100),
) -> AdvisorHistoryList:
    if not get_settings().advisor_engine_enabled:
        return AdvisorHistoryList(items=[])
    items = await service.list_history(session, brand_id=tenant.brand_id, limit=limit)
    return AdvisorHistoryList(items=items)


@router.get("/effectiveness", response_model=EffectivenessResponse)
async def get_effectiveness(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> EffectivenessResponse:
    if not get_settings().advisor_outcome_learning_enabled:
        return EffectivenessResponse(channels=[])
    rows = await list_effectiveness(session, brand_id=tenant.brand_id)
    return EffectivenessResponse(
        channels=[EffectivenessChannel(**r) for r in rows]
    )


@router.get("/intelligence", response_model=IntelligenceReport)
async def get_intelligence(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> IntelligenceReport:
    if not get_settings().advisor_intelligence_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence engine is disabled",
        )
    profile = await _require_profile(session, tenant)

    cache_key = f"advisor:intelligence:{tenant.brand_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return IntelligenceReport.model_validate(cached)

    report = await compose_intelligence(session, profile=profile, tenant=tenant)
    await cache_set(
        cache_key,
        report.model_dump(mode="json"),
        ttl_seconds=1800,
    )
    return report


@router.get("/brain", response_model=BusinessBrainResponse)
async def get_brain(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> BusinessBrainResponse:
    profile = await _require_profile(session, tenant)
    brain = load_business_brain(profile)
    score, steps = brain_completeness(brain)
    return BusinessBrainResponse(
        industry=brain.industry,
        business_type=brain.business_type,
        target_audience=brain.target_audience,
        monthly_budget=brain.monthly_budget,
        growth_goal=brain.growth_goal,
        location=brain.location,
        competitors=brain.competitors,
        completeness_score=score,
        missing_steps=steps,
    )


@router.patch("/brain", response_model=BusinessBrainResponse)
async def update_brain(
    payload: BusinessBrainUpdate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> BusinessBrainResponse:
    update = BusinessProfileUpdate(
        industry=payload.industry,
        business_type=payload.business_type,
        target_audience=payload.target_audience,
        monthly_budget_band=payload.monthly_budget_band,
        primary_goal_text=payload.primary_goal_text,
        business_location=payload.business_location,
        competitors=payload.competitors,
    )
    row, _ = await onboarding_service.update_profile(
        session, tenant=tenant, payload=update
    )
    profile = row
    brain = load_business_brain(profile)
    score, steps = brain_completeness(brain)
    return BusinessBrainResponse(
        industry=brain.industry,
        business_type=brain.business_type,
        target_audience=brain.target_audience,
        monthly_budget=brain.monthly_budget,
        growth_goal=brain.growth_goal,
        location=brain.location,
        competitors=brain.competitors,
        completeness_score=score,
        missing_steps=steps,
    )


@router.post("/execute", response_model=ExecuteRecommendationResponse)
async def post_execute(
    payload: ExecuteRecommendationRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> ExecuteRecommendationResponse:
    if not get_settings().advisor_engine_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Advisor engine is disabled",
        )
    return await execute_recommendation(
        session, tenant=tenant, recommendation_id=payload.recommendation_id
    )


@router.post("/execute/schedule", response_model=ScheduledPostResponse)
async def post_execute_schedule(
    payload: ScheduleFromRecommendationRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ScheduledPostResponse:
    from aicmo.modules.publishing import service as publishing_service

    return await publishing_service.schedule_from_recommendation(
        session, tenant=tenant, payload=payload
    )


@router.get("/agent/{report_type}", response_model=AgentReport)
async def get_agent_report(
    report_type: AgentReportType,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AgentReport:
    if not get_settings().advisor_agent_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Marketing agent is disabled",
        )
    profile = await _require_profile(session, tenant)
    return await generate_agent_report(
        session, profile=profile, tenant=tenant, report_type=report_type
    )


@router.patch(
    "/recommendations/{recommendation_id}",
    response_model=AdvisorRecommendationResponse,
)
async def update_recommendation_status(
    recommendation_id: uuid.UUID,
    payload: UpdateRecommendationStatusRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AdvisorRecommendationResponse:
    if not get_settings().advisor_engine_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Advisor engine is disabled",
        )
    return await service.update_status(
        session,
        tenant=tenant,
        recommendation_id=recommendation_id,
        status=payload.status,
    )
