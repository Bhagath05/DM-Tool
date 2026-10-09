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
from datetime import datetime

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
from aicmo.modules.learning import service as learning_service
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
from aicmo.modules.strategist import service as strategist_service

_ANALYTICS_VIEW = "analytics.view"
# Matches the learning (Learning Lab) read endpoints' own gate so a user who can
# read experiments via the API can read them via the tool, and no further.
_LIBRARY_VIEW = "library.view"


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


class ExperimentsInput(ToolInput):
    limit: int = Field(default=10, ge=1, le=50, description="How many recent experiments to return.")


# --- typed result wrappers for services that return rows/dicts --------------
class RecommendationsResult(BaseModel):
    items: list[MarketingBrainRecommendationRef]


class OutcomesResult(BaseModel):
    items: list[MarketingBrainOutcomeItem]


class LearningInsightsResult(BaseModel):
    items: list[MarketingBrainLearningItem]


class AgentStrategyView(BaseModel):
    """Bounded view of the brand's current marketing strategy. `present=False`
    when none exists — never fabricated. SYSTEM_INFERRED: derived from the
    profile, not measured."""

    present: bool
    status: str | None = None
    positioning: str | None = None
    target_summary: str | None = None
    recommendation: str | None = None
    reason: str | None = None
    expected_result: str | None = None
    campaign_roadmap: list[str] = Field(default_factory=list)


class AgentExperimentView(BaseModel):
    """Decision-relevant fields of one experiment — the verbose internal
    snapshots (context/variable dicts) are deliberately NOT surfaced to the
    model. `confidence_score`/`sample_size` are measured, never invented."""

    id: uuid.UUID
    hypothesis: str | None = None
    goal: str | None = None
    platform: str | None = None
    status: str
    sample_size: int
    confidence_score: float
    created_at: datetime


class ExperimentsResult(BaseModel):
    items: list[AgentExperimentView]


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


async def _get_marketing_strategy(ctx: ExecutionContext, _inp: BaseModel) -> AgentStrategyView:
    """The brand's CURRENT strategy (latest record). Reuses strategist.latest —
    pure brand-scoped DB read, no generation. present=False when none exists."""
    record = await strategist_service.latest(ctx.session, brand_id=_brand(ctx))
    strategy = getattr(record, "strategy", None)
    if record is None or not isinstance(strategy, dict) or not strategy:
        return AgentStrategyView(present=False)
    roadmap = strategy.get("campaign_roadmap")
    return AgentStrategyView(
        present=True,
        status=getattr(record, "status", None),
        positioning=strategy.get("positioning"),
        target_summary=strategy.get("target_summary"),
        recommendation=strategy.get("recommendation"),
        reason=strategy.get("reason"),
        expected_result=strategy.get("expected_result"),
        campaign_roadmap=[str(x) for x in roadmap][:6] if isinstance(roadmap, list) else [],
    )


async def _get_experiments(ctx: ExecutionContext, inp: ExperimentsInput) -> ExperimentsResult:
    """Recent experiments this brand has run. Reuses learning.list_experiments —
    pure brand-scoped DB read. Surfaces only decision-relevant fields; measured
    sample_size/confidence are reported as-is, never invented."""
    rows = await learning_service.list_experiments(
        ctx.session, brand_id=_brand(ctx), limit=inp.limit
    )
    return ExperimentsResult(
        items=[
            AgentExperimentView(
                id=r.id,
                hypothesis=r.hypothesis,
                goal=r.goal,
                platform=r.platform,
                status=r.status,
                sample_size=r.sample_size,
                confidence_score=r.confidence_score,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


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
        name="get_marketing_strategy",
        description=(
            "The brand's CURRENT marketing strategy: positioning, who to target, "
            "the single highest-leverage move, and the campaign roadmap. Use for "
            "'what is our strategy' / 'what should our plan be'. Returns "
            "present=false when no strategy has been generated yet — never invents one."
        ),
        category="strategy",
        operation_class=OperationClass.READ,
        input_schema=EmptyInput,
        output_schema=AgentStrategyView,
        handler=_get_marketing_strategy,
        permission=_ANALYTICS_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Derived strategy (SYSTEM_INFERRED), not a measured outcome.",
    ),
    ToolDefinition(
        name="get_experiments",
        description=(
            "Recent marketing experiments this brand has run (hypothesis, platform, "
            "status, sample size, confidence). Use for 'what did our previous "
            "experiments teach us' or to compare tested approaches. Reports measured "
            "sample size/confidence as-is and never claims an experiment succeeded "
            "without a measured result."
        ),
        category="learning",
        operation_class=OperationClass.READ,
        input_schema=ExperimentsInput,
        output_schema=ExperimentsResult,
        handler=_get_experiments,
        permission=_LIBRARY_VIEW,
        tenant_scope=TenantScope.BRAND,
        provenance=True,
        provenance_note="Measured experiment records; successes require evaluated results.",
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
