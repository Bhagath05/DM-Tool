"""Compose MarketingBrainContext from existing brand-scoped sources.

Read-only. Brand scope always comes from TenantContext — never from a
caller-supplied brand_id alone.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.memory import load_brand_memory
from aicmo.modules.advisor.outcomes import load_outcome_context
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.business_brain import service as bb_service
from aicmo.modules.business_brain.models import BrainEvidence
from aicmo.modules.business_brain.research_service import _require_brand
from aicmo.modules.business_brain.schemas import EvidenceItem
from aicmo.modules.learning.feedback import active_insights_for_module
from aicmo.modules.marketing_brain.schemas import (
    MarketingBrainAnalyticsSnapshot,
    MarketingBrainContext,
    MarketingBrainLearningItem,
    MarketingBrainOutcomeItem,
    MarketingBrainProfileSnapshot,
    MarketingBrainRecommendationRef,
    MarketingBrainResearchSnapshot,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext

# Caps keep prompt/context bounded and deterministic.
_EVIDENCE_LIMIT = 100
_RECOMMENDATION_LIMIT = 25
_LEARNING_LIMIT = 12
_PROMPT_FACT_CAP = 12
_PROMPT_OBS_CAP = 8
_PROMPT_HYP_CAP = 6
_PROMPT_ICP_CAP = 5
_PROMPT_LEARNING_CAP = 6


async def build_context(
    session: AsyncSession,
    *,
    tenant: TenantContext,
) -> MarketingBrainContext:
    """Assemble unified marketing context for the active tenant brand.

    Raises HTTP 400 when no brand is selected (same contract as Business Brain).
    Never loads another brand's rows.
    """
    brand_id = _require_brand(tenant)
    built_at = datetime.now(UTC)

    summary = await bb_service.get_context(session, tenant=tenant)
    evidence_resp = await bb_service.list_evidence(session, tenant=tenant, limit=_EVIDENCE_LIMIT)
    icps_resp = await bb_service.get_icp_hypotheses(session, tenant=tenant)
    competitors = await bb_service.list_competitors(session, tenant=tenant)
    market = await bb_service.list_market_signals(session, tenant=tenant)

    facts: list[EvidenceItem] = []
    observations: list[EvidenceItem] = []
    hypotheses: list[EvidenceItem] = []
    evidence_recommendations: list[EvidenceItem] = []
    for item in evidence_resp.items:
        if item.kind == "fact":
            facts.append(item)
        elif item.kind == "observation":
            observations.append(item)
        elif item.kind == "hypothesis":
            hypotheses.append(item)
        elif item.kind == "recommendation":
            evidence_recommendations.append(item)

    superseded_excluded_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(BrainEvidence)
                .where(
                    BrainEvidence.brand_id == brand_id,
                    BrainEvidence.status.in_(("superseded", "contradicted")),
                )
            )
        ).scalar_one()
        or 0
    )

    profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    if profile_row is None:
        profile = MarketingBrainProfileSnapshot(present=False)
    else:
        primary_goal = profile_row.primary_goal_text or (
            profile_row.goals[0] if profile_row.goals else None
        )
        profile = MarketingBrainProfileSnapshot(
            present=True,
            business_name=profile_row.business_name,
            website=profile_row.website,
            industry=profile_row.industry,
            business_type=profile_row.business_type,
            target_audience=profile_row.target_audience,
            location=profile_row.business_location,
            competitors=list(profile_row.competitors or []),
            monthly_budget_band=profile_row.monthly_budget_band,
            primary_goal=primary_goal,
        )

    analytics_snap: MarketingBrainAnalyticsSnapshot | None = None
    try:
        overview = await analytics_service.overview(session, brand_id=brand_id)
        analytics_snap = MarketingBrainAnalyticsSnapshot(
            total_leads=overview.total_leads,
            leads_7d=overview.leads_7d,
            leads_30d=overview.leads_30d,
            hot_leads=overview.hot_leads,
            conversion_rate=overview.conversion_rate,
            landing_pages_published=overview.landing_pages_published,
            total_views=overview.total_views,
            total_submissions=overview.total_submissions,
        )
    except Exception:
        analytics_snap = None

    rec_rows = await load_brand_memory(session, brand_id=brand_id, days=90)
    recommendations = [
        MarketingBrainRecommendationRef(
            id=r.id,
            title=r.title,
            status=r.status,
            source_surface=r.source_surface,
            confidence=r.confidence,
            impact_category=r.impact_category,
            expected_result=r.expected_result,
            created_at=r.created_at,
            updated_at=r.updated_at,
            completed_at=r.completed_at,
            skipped_at=r.skipped_at,
            outcome_summary=r.outcome_summary,
        )
        for r in rec_rows[:_RECOMMENDATION_LIMIT]
    ]

    outcome_ctx = await load_outcome_context(session, brand_id=brand_id)
    outcomes: list[MarketingBrainOutcomeItem] = []
    for o in outcome_ctx.get("recent_outcomes") or []:
        outcomes.append(
            MarketingBrainOutcomeItem(
                title=str(o.get("title") or ""),
                delta_summary=o.get("delta_summary"),
                effectiveness_score=o.get("effectiveness_score"),
                source_surface=o.get("source_surface"),
                kind="evaluated_success",
            )
        )
    for o in outcome_ctx.get("failed_outcomes") or []:
        outcomes.append(
            MarketingBrainOutcomeItem(
                title=str(o.get("title") or ""),
                delta_summary=o.get("delta_summary") or o.get("reason"),
                kind="failed_or_skipped",
            )
        )

    # Cross-domain lessons that influence business understanding — not BB facts.
    learning_rows = await active_insights_for_module(
        session,
        brand_id=brand_id,
        module="business_understanding",
        limit=_LEARNING_LIMIT,
    )
    learning_insights = [
        MarketingBrainLearningItem(
            id=row.id,
            category=row.category,
            observation=row.observation,
            recommendation=row.recommendation,
            expected_result=row.expected_result,
            confidence=row.confidence,
            direction=row.direction,
            status=row.status,
            learned_at=row.learned_at,
            expires_at=row.expires_at,
            evidence=list(row.evidence or []),
        )
        for row in learning_rows
    ]

    research = MarketingBrainResearchSnapshot(
        latest_website_job=summary.latest_website_job,
        latest_competitor_job=summary.latest_competitor_job,
        latest_market_job=summary.latest_market_job,
        competitor_candidates=list(competitors.candidates),
        competitor_status=competitors.status,
        competitor_message=competitors.message,
        market_signals=list(market.signals),
        market_status=market.status,
        market_message=market.message,
    )

    limitations = list(summary.limitations)
    limitations.append(
        "Hypotheses and ICP rows are not confirmed facts — do not state them as certainty."
    )
    limitations.append(
        "Learning insights are lessons from past performance, not Business Brain evidence."
    )
    if analytics_snap is None:
        limitations.append("Analytics overview was unavailable for this context build.")
    if superseded_excluded_count:
        limitations.append(
            f"{superseded_excluded_count} superseded/contradicted evidence row(s) "
            "excluded from active context."
        )

    return MarketingBrainContext(
        brand_id=brand_id,
        organization_id=tenant.organization_id,
        built_at=built_at,
        profile=profile,
        known=list(summary.known),
        unknown=list(summary.unknown),
        limitations=limitations,
        facts=facts,
        observations=observations,
        hypotheses=hypotheses,
        evidence_recommendations=evidence_recommendations,
        evidence_counts=dict(summary.evidence_counts),
        superseded_excluded_count=superseded_excluded_count,
        icps=list(icps_resp.items),
        icp_status=icps_resp.status,
        icp_message=icps_resp.message,
        research=research,
        analytics=analytics_snap,
        recommendations=recommendations,
        outcomes=outcomes,
        learning_insights=learning_insights,
    )


def context_to_prompt_block(ctx: MarketingBrainContext) -> str:
    """Deterministic, kind-labeled prompt fragment for LLM injection.

    Never presents hypotheses as facts. Empty sections stay explicit.
    """
    lines = [
        "=== MARKETING BRAIN CONTEXT (composed; do not invent missing fields) ===",
        f"Brand: {ctx.brand_id}",
        f"Known: {', '.join(ctx.known) if ctx.known else '(none)'}",
        f"Unknown: {', '.join(ctx.unknown) if ctx.unknown else '(none)'}",
    ]
    if ctx.profile.present:
        lines.append(
            f"Profile: {ctx.profile.business_name or 'unnamed'} | "
            f"industry={ctx.profile.industry or 'unknown'} | "
            f"audience={ctx.profile.target_audience or 'unknown'}"
        )
    else:
        lines.append("Profile: MISSING — no business profile for this brand.")

    lines.append("")
    lines.append("FACTS (Business Brain — confirmed-style claims with provenance):")
    if not ctx.facts:
        lines.append("- (none)")
    else:
        for e in ctx.facts[:_PROMPT_FACT_CAP]:
            lines.append(_evidence_line("FACT", e))

    lines.append("OBSERVATIONS (Business Brain — seen signals, not conclusions):")
    if not ctx.observations:
        lines.append("- (none)")
    else:
        for e in ctx.observations[:_PROMPT_OBS_CAP]:
            lines.append(_evidence_line("OBSERVATION", e))

    lines.append("HYPOTHESES (Business Brain — NOT facts; do not assert as true):")
    if not ctx.hypotheses:
        lines.append("- (none)")
    else:
        for e in ctx.hypotheses[:_PROMPT_HYP_CAP]:
            lines.append(_evidence_line("HYPOTHESIS", e))

    lines.append("ICP HYPOTHESES (audience WHO — status preserved):")
    if not ctx.icps:
        lines.append(f"- (none) [{ctx.icp_status}] {ctx.icp_message or ''}".rstrip())
    else:
        for icp in ctx.icps[:_PROMPT_ICP_CAP]:
            lines.append(
                f"- [{icp.status.upper()}] {icp.name} "
                f"(confidence {icp.confidence}%): {icp.description[:200]}"
            )

    if ctx.research.competitor_candidates:
        lines.append("COMPETITOR CANDIDATES (research — not verified CRM firms):")
        for c in ctx.research.competitor_candidates[:5]:
            lines.append(f"- [{c.status}] {c.name} (confidence {c.confidence}%): {c.reason[:160]}")
    else:
        lines.append(f"COMPETITOR CANDIDATES: none ({ctx.research.competitor_status})")

    if ctx.research.market_signals:
        lines.append("MARKET SIGNALS (research):")
        for s in ctx.research.market_signals[:6]:
            lines.append(
                f"- [{s.evidence_kind}] {s.signal_kind}: {s.claim[:180]} "
                f"(confidence {s.confidence}%)"
            )
    else:
        lines.append(f"MARKET SIGNALS: none ({ctx.research.market_status})")

    if ctx.analytics is not None:
        a = ctx.analytics
        lines.append(
            "ANALYTICS (internal KPIs): "
            f"leads_7d={a.leads_7d}, leads_30d={a.leads_30d}, "
            f"hot={a.hot_leads}, conversion={a.conversion_rate:.1%}"
        )
    else:
        lines.append("ANALYTICS: unavailable")

    lines.append("ADVISOR RECOMMENDATIONS (tasks — not Business Brain evidence):")
    if not ctx.recommendations:
        lines.append("- (none)")
    else:
        for r in ctx.recommendations[:8]:
            lines.append(f"- [{r.status}] {r.title[:120]} (confidence {r.confidence}%)")

    lines.append("OUTCOMES (evaluated / skipped — distinct from evidence):")
    if not ctx.outcomes:
        lines.append("- (none)")
    else:
        for o in ctx.outcomes[:6]:
            lines.append(f"- [{o.kind}] {o.title}: {o.delta_summary or 'n/a'}")

    lines.append("LEARNING INSIGHTS (lessons — not Business Brain facts):")
    if not ctx.learning_insights:
        lines.append("- (none)")
    else:
        for li in ctx.learning_insights[:_PROMPT_LEARNING_CAP]:
            lines.append(
                f"- [{li.direction}/{li.category}] {li.observation[:160]} "
                f"(confidence {li.confidence}%)"
            )

    if ctx.limitations:
        lines.append("LIMITATIONS:")
        for lim in ctx.limitations[:8]:
            lines.append(f"- {lim}")

    return "\n".join(lines)


def _evidence_line(label: str, e: EvidenceItem) -> str:
    src = e.source_url or e.source_type
    when = e.discovered_at.isoformat() if e.discovered_at else "unknown"
    return (
        f"- [{label}] ({e.category}) {e.claim[:220]} "
        f"[confidence={e.confidence}% status={e.status} source={src} at={when}]"
    )
