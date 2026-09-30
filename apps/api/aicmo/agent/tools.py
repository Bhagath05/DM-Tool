"""Built-in READ-only tools — the initial Tool Registry surface.

Every handler is a THIN adapter over an EXISTING domain service. No business
logic, no new DB queries, no parallel implementations. Tenant/session authority
always comes from ``ExecutionContext`` (server-derived); tool inputs carry only
business parameters, never a tenant/brand id.

Phase 1 registers READ tools only. WRITE and CONSEQUENTIAL are supported by the
contract (and tested with synthetic tools), but no consequential tool is
registered or executed here — that boundary belongs to Phase 2.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from aicmo.agent.registry import ToolRegistry
from aicmo.agent.types import (
    ExecutionContext,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolInput,
)
from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative
from aicmo.modules.advisor.memory import load_brand_memory
from aicmo.modules.advisor.outcomes import load_outcome_context
from aicmo.modules.advisor.schemas import CreativeEvaluationResponse
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.analytics.schemas import OverviewKpis
from aicmo.modules.business_brain import service as bb_service
from aicmo.modules.business_brain.schemas import (
    CompetitorResearchResponse,
    IcpListResponse,
    MarketResearchResponse,
)
from aicmo.modules.insights import service as insights_service
from aicmo.modules.insights.schemas import InsightFeedResponse
from aicmo.modules.learning.feedback import active_insights_for_module
from aicmo.modules.marketing_brain import service as mb_service
from aicmo.modules.marketing_brain.schemas import (
    MarketingBrainContext,
    MarketingBrainLearningItem,
    MarketingBrainOutcomeItem,
    MarketingBrainProfileSnapshot,
    MarketingBrainRecommendationRef,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.performance import service as performance_service
from aicmo.modules.performance.schemas import PerformanceOverview

_ANALYTICS_VIEW = "analytics.view"


def _brand(ctx: ExecutionContext) -> uuid.UUID:
    """The active brand id. BRAND-scoped tools are authorized only when a brand
    is present (the registry enforces it), so this narrows away the Optional."""
    brand_id = ctx.tenant.brand_id
    if brand_id is None:  # defensive — should be unreachable for BRAND tools
        raise RuntimeError("brand-scoped tool executed without an active brand")
    return brand_id


# --- input schemas (business parameters only — never tenant/brand) ----------
class EmptyInput(ToolInput):
    """No parameters — the read is fully determined by the execution context."""


class RecommendationsInput(ToolInput):
    days: int = Field(default=90, ge=1, le=365, description="Look-back window in days.")


class OutcomesInput(ToolInput):
    limit: int = Field(default=10, ge=1, le=50)


class LearningInsightsInput(ToolInput):
    module: str = Field(default="business_understanding", max_length=64)
    limit: int = Field(default=6, ge=1, le=50)


class MarketingInsightsInput(ToolInput):
    category: str | None = Field(default=None, max_length=64)
    min_severity: str | None = Field(default=None, max_length=32)
    channel: str | None = Field(default=None, max_length=64)
    objective: str | None = Field(default=None, max_length=64)


# --- typed result wrappers for services that return rows/dicts --------------
class RecommendationsResult(BaseModel):
    items: list[MarketingBrainRecommendationRef]


class OutcomesResult(BaseModel):
    items: list[MarketingBrainOutcomeItem]


class LearningInsightsResult(BaseModel):
    items: list[MarketingBrainLearningItem]


# --- handlers (thin adapters over existing services) ------------------------
async def _get_marketing_context(ctx: ExecutionContext, _inp: BaseModel) -> MarketingBrainContext:
    return await mb_service.build_context(ctx.session, tenant=ctx.tenant)


async def _get_business_profile(ctx: ExecutionContext, _inp: BaseModel) -> MarketingBrainProfileSnapshot:
    row = await onboarding_service.get_profile_or_none(ctx.session, _brand(ctx))
    return mb_service.build_profile_snapshot(row)


async def _get_icp_evidence(ctx: ExecutionContext, _inp: BaseModel) -> IcpListResponse:
    return await bb_service.get_icp_hypotheses(ctx.session, tenant=ctx.tenant)


async def _get_competitor_context(ctx: ExecutionContext, _inp: BaseModel) -> CompetitorResearchResponse:
    return await bb_service.list_competitors(ctx.session, tenant=ctx.tenant)


async def _get_market_signals(ctx: ExecutionContext, _inp: BaseModel) -> MarketResearchResponse:
    return await bb_service.list_market_signals(ctx.session, tenant=ctx.tenant)


async def _get_campaign_performance(ctx: ExecutionContext, _inp: BaseModel) -> OverviewKpis:
    return await analytics_service.overview(ctx.session, brand_id=_brand(ctx))


async def _get_content_performance(ctx: ExecutionContext, _inp: BaseModel) -> PerformanceOverview:
    return await performance_service.overview(ctx.session, tenant=ctx.tenant)


async def _get_marketing_insights(ctx: ExecutionContext, inp: MarketingInsightsInput) -> InsightFeedResponse:
    return await insights_service.build_feed(
        ctx.session,
        tenant=ctx.tenant,
        category=inp.category,
        min_severity=inp.min_severity,
        channel=inp.channel,
        objective=inp.objective,
    )


async def _get_recommendations(ctx: ExecutionContext, inp: RecommendationsInput) -> RecommendationsResult:
    rows = await load_brand_memory(ctx.session, brand_id=_brand(ctx), days=inp.days)
    return RecommendationsResult(items=mb_service.to_recommendation_refs(rows))


async def _get_outcomes(ctx: ExecutionContext, inp: OutcomesInput) -> OutcomesResult:
    outcome_ctx = await load_outcome_context(ctx.session, brand_id=_brand(ctx), limit=inp.limit)
    return OutcomesResult(items=mb_service.to_outcome_items(outcome_ctx))


async def _get_learning_insights(ctx: ExecutionContext, inp: LearningInsightsInput) -> LearningInsightsResult:
    rows = await active_insights_for_module(
        ctx.session, brand_id=_brand(ctx), module=inp.module, limit=inp.limit
    )
    return LearningInsightsResult(items=mb_service.to_learning_items(rows))


async def _evaluate_creative(ctx: ExecutionContext, _inp: BaseModel) -> CreativeEvaluationResponse:
    # Advisory READ — the evaluator never publishes or spends.
    return await evaluate_creative(ctx.session, tenant=ctx.tenant)


# --- the built-in tool set --------------------------------------------------
BUILTIN_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_marketing_context",
        description="The canonical, evidence-labelled marketing context for the active brand "
        "(business profile, evidence, ICP, competitors, market, analytics, recommendations, learning).",
        category="business_context",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=MarketingBrainContext,
        handler=_get_marketing_context,
        permission=None,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Composed from Business Brain evidence, analytics, advisor memory, and learning.",
    ),
    ToolDefinition(
        name="get_business_profile",
        description="The active brand's first-party business profile (industry, audience, products, "
        "services, pricing, channels, goals) — owner-declared, never fabricated.",
        category="business_context",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=MarketingBrainProfileSnapshot,
        handler=_get_business_profile,
        permission=None,
        tenant_scope=TenantScope.BRAND,
        provenance=False,
        provenance_note="Owner-declared profile; not externally sourced.",
    ),
    ToolDefinition(
        name="get_icp_evidence",
        description="ICP hypotheses and their Business Brain evidence for the active brand.",
        category="business_context",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=IcpListResponse,
        handler=_get_icp_evidence,
        permission=None,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="ICP hypotheses with linked evidence and confidence/status.",
    ),
    ToolDefinition(
        name="get_competitor_context",
        description="Competitor research candidates for the active brand (with confidence + status).",
        category="business_context",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=CompetitorResearchResponse,
        handler=_get_competitor_context,
        permission=None,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Research candidates; INSUFFICIENT_EVIDENCE when none.",
    ),
    ToolDefinition(
        name="get_market_signals",
        description="Market/demand research signals for the active brand (evidence kind + confidence).",
        category="business_context",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=MarketResearchResponse,
        handler=_get_market_signals,
        permission=None,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Research signals; INSUFFICIENT_EVIDENCE when none.",
    ),
    ToolDefinition(
        name="get_campaign_performance",
        description="First-party internal analytics KPIs for the active brand (leads, conversion, views).",
        category="analytics",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=OverviewKpis,
        handler=_get_campaign_performance,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="First-party measured analytics — no estimates.",
    ),
    ToolDefinition(
        name="get_content_performance",
        description="First-party content/creative performance overview for the active brand.",
        category="analytics",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=PerformanceOverview,
        handler=_get_content_performance,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="First-party measured content performance.",
    ),
    ToolDefinition(
        name="get_marketing_insights",
        description="Ranked marketing insights for the active brand, with contributing source surfaces.",
        category="analytics",
        operation_class=OperationClass.READ,
        input_schema=MarketingInsightsInput,
        output_schema=InsightFeedResponse,
        handler=_get_marketing_insights,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Insights carry their contributing source surfaces.",
    ),
    ToolDefinition(
        name="get_recommendations",
        description="Advisor recommendations for the active brand (title, status, confidence, impact).",
        category="learning",
        operation_class=OperationClass.READ,
        input_schema=RecommendationsInput,
        output_schema=RecommendationsResult,
        handler=_get_recommendations,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Advisor recommendations with confidence.",
    ),
    ToolDefinition(
        name="get_outcomes",
        description="Evaluated recommendation outcomes and effectiveness for the active brand.",
        category="learning",
        operation_class=OperationClass.READ,
        input_schema=OutcomesInput,
        output_schema=OutcomesResult,
        handler=_get_outcomes,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Outcomes with delta summaries + effectiveness.",
    ),
    ToolDefinition(
        name="get_learning_insights",
        description="Validated learning insights (lessons) for the active brand.",
        category="learning",
        operation_class=OperationClass.READ,
        input_schema=LearningInsightsInput,
        output_schema=LearningInsightsResult,
        handler=_get_learning_insights,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Learning insights with evidence and confidence.",
    ),
    ToolDefinition(
        name="evaluate_creative",
        description="Advisory AI-vs-human creative evaluation for the active brand — never publishes or spends.",
        category="creative",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=CreativeEvaluationResponse,
        handler=_evaluate_creative,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Provenance-labelled AI-vs-human evidence; advisory only.",
    ),
]


def register_builtin_tools(registry: ToolRegistry) -> None:
    for definition in BUILTIN_TOOLS:
        registry.register_tool(definition)


_DEFAULT_REGISTRY: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """The process-wide read-only tool registry (built once)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
