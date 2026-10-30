"""Unified signal gatherer — every recommendation must load these first."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.brain import (
    BusinessBrain,
    brain_completeness,
    brain_has_minimum,
    brain_to_prompt_block,
    load_business_brain,
)
from aicmo.modules.advisor.connectors import load_connector_context
from aicmo.modules.advisor.content_intelligence import load_content_intelligence
from aicmo.modules.advisor.lead_context import load_lead_context
from aicmo.modules.advisor.outcomes import load_outcome_context
from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.belief.grounding import EvidenceGrounding
from aicmo.modules.marketing_analytics import service as marketing_analytics_service
from aicmo.modules.marketing_analytics.schemas import AdvisorAnalyticsSignal
from aicmo.modules.marketing_analytics.signal_prompt import signal_to_prompt_block
from aicmo.modules.marketing_brain.schemas import MarketingBrainContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


@dataclass
class IntelligenceSignals:
    brain: BusinessBrain
    brain_complete: bool
    setup_steps: list[str]
    outcome_context: dict
    connector_context: dict
    content_intelligence: dict
    lead_context: dict
    analytics_signals: list[str]
    data_sources: list[DataSourceRef] = field(default_factory=list)
    has_outcomes: bool = False
    has_connectors: bool = False
    has_content_intel: bool = False
    has_lead_intel: bool = False
    activity_signals: int = 0
    # Phase 4 — read-only computed platform analytics feed (marketing_analytics).
    analytics_signal: AdvisorAnalyticsSignal | None = None
    # Phase A — unified Marketing Brain context (BB evidence + ICP + learning…).
    # Optional: composition failures must never abort intelligence.
    marketing_brain: MarketingBrainContext | None = None
    # Phase 7.16 — the brand's evidence-graded beliefs (what it has LEARNED), as
    # a prompt block + structured provenance. Optional + defensive: a grounding
    # failure must never abort recommendation generation.
    belief_block: str = ""
    belief_grounding: EvidenceGrounding | None = None


async def gather_intelligence_signals(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    tenant: TenantContext | None = None,
    brand_id: uuid.UUID | None = None,
) -> IntelligenceSignals:
    """Load profile brain → Marketing Brain context → Outcomes → Connectors → …

    Prefer `tenant=` so brand scope is authorization-derived. `brand_id=` remains
    for legacy script callers but must match `tenant.brand_id` when both are set.
    """
    resolved_brand = _resolve_brand_id(tenant=tenant, brand_id=brand_id)
    brain = load_business_brain(profile)
    _, setup_steps = brain_completeness(brain)

    marketing_brain: MarketingBrainContext | None = None
    belief_block = ""
    belief_grounding: EvidenceGrounding | None = None
    if tenant is not None and tenant.brand_id is not None:
        try:
            from aicmo.modules.marketing_brain.service import build_context

            marketing_brain = await build_context(session, tenant=tenant)
        except Exception as e:  # never abort advisor for a context compose miss
            log.warning("advisor.marketing_brain_context_failed", error=str(e)[:200])
        # Phase 7.16 — ground recommendations in the brand's evidence-graded
        # beliefs (reuses the shared belief-grounding foundation). Defensive: a
        # grounding failure must never abort recommendation generation.
        try:
            from aicmo.modules.belief.grounding import resolve_evidence_grounding

            belief_block, belief_grounding = await resolve_evidence_grounding(
                session, tenant=tenant
            )
        except Exception as e:
            log.warning("advisor.belief_grounding_failed", error=str(e)[:200])

    outcome_ctx = await load_outcome_context(session, brand_id=resolved_brand)
    connector_ctx = await load_connector_context(session, brand_id=resolved_brand)
    content_ctx = await load_content_intelligence(session, brand_id=resolved_brand)
    lead_ctx = await load_lead_context(session, brand_id=resolved_brand)
    overview = await analytics_service.overview(session, brand_id=resolved_brand)

    # Phase 4 — read-only, computed platform analytics. Wrapped so an analytics
    # failure can never break recommendation generation; degrades to None.
    analytics_signal = None
    try:
        analytics_signal = await marketing_analytics_service.advisor_signal(
            session, brand_id=resolved_brand
        )
    except Exception as e:  # never abort the advisor for an analytics read
        log.warning("advisor.analytics_signal_failed", error=str(e)[:200])
    analytics_signals = [
        f"Total leads: {overview.total_leads}",
        f"Leads (7d): {overview.leads_7d}",
        f"Leads (30d): {overview.leads_30d}",
        f"Hot leads: {overview.hot_leads}",
    ]
    if overview.conversion_rate > 0:
        analytics_signals.append(f"Landing page conversion: {overview.conversion_rate:.1%}")

    data_sources: list[DataSourceRef] = [
        DataSourceRef(key="leads_7d", label="Leads (7 days)", value=str(overview.leads_7d)),
        DataSourceRef(key="leads_30d", label="Leads (30 days)", value=str(overview.leads_30d)),
        DataSourceRef(key="hot_leads", label="Hot leads", value=str(overview.hot_leads)),
    ]
    data_sources.extend(connector_ctx.get("data_sources", []))
    data_sources.extend(content_ctx.get("data_sources", []))
    data_sources.extend(lead_ctx.get("data_sources", []))
    # Phase 7.16 — surface the evidence that grounded this run as data sources
    # (explainable provenance) without inventing anything: each is a real,
    # server-derived belief with its confidence.
    if belief_grounding is not None:
        for b in belief_grounding.beliefs[:5]:
            data_sources.append(
                DataSourceRef(
                    key=f"belief:{b.subject_key}",
                    label=f"Learned: {b.statement[:80]}",
                    value=f"{b.confidence}% confident ({b.evidence_count} evidence)",
                )
            )

    activity_signals = sum(
        1 for n in (overview.total_leads, overview.leads_7d, overview.leads_30d) if n > 0
    )

    return IntelligenceSignals(
        brain=brain,
        brain_complete=brain_has_minimum(brain),
        setup_steps=setup_steps,
        outcome_context=outcome_ctx,
        connector_context=connector_ctx,
        content_intelligence=content_ctx,
        lead_context=lead_ctx,
        analytics_signals=analytics_signals,
        data_sources=data_sources,
        has_outcomes=bool(outcome_ctx.get("recent_outcomes")),
        has_connectors=connector_ctx.get("has_data", False),
        has_content_intel=content_ctx.get("has_data", False),
        has_lead_intel=lead_ctx.get("has_data", False),
        activity_signals=activity_signals,
        analytics_signal=analytics_signal,
        marketing_brain=marketing_brain,
        belief_block=belief_block,
        belief_grounding=belief_grounding,
    )


def _resolve_brand_id(*, tenant: TenantContext | None, brand_id: uuid.UUID | None) -> uuid.UUID:
    if tenant is not None and tenant.brand_id is not None:
        if brand_id is not None and brand_id != tenant.brand_id:
            raise ValueError(
                "brand_id does not match tenant.brand_id — refusing cross-brand context"
            )
        return tenant.brand_id
    if brand_id is not None:
        return brand_id
    raise ValueError("gather_intelligence_signals requires tenant.brand_id or brand_id")


def signals_to_prompt_block(signals: IntelligenceSignals, *, confidence_cap: int) -> str:
    """Build LLM context in mandatory priority order."""
    parts = [
        f"CONFIDENCE CAP: Do not exceed {confidence_cap}. Never invent metrics.",
        "",
        "=== 1. BUSINESS BRAIN (required) ===",
        brain_to_prompt_block(signals.brain),
        "",
    ]
    if signals.marketing_brain is not None:
        from aicmo.modules.marketing_brain.service import context_to_prompt_block

        parts.extend(
            [
                context_to_prompt_block(signals.marketing_brain),
                "",
            ]
        )
    # Phase 7.16 — what this brand has LEARNED (evidence-graded beliefs). Treat a
    # high-confidence ACTIVE belief as established; never contradict one without
    # flagging it; when this is INSUFFICIENT_EVIDENCE, frame picks as hypotheses.
    parts.extend(
        [
            "=== LEARNED BELIEFS (evidence-graded; validated findings vs hypotheses) ===",
            signals.belief_block
            or "(no validated beliefs yet — INSUFFICIENT_EVIDENCE; recommend as hypotheses to test)",
            "",
        ]
    )
    parts.extend(
        [
            "=== 2. HISTORICAL OUTCOMES (what worked / failed) ===",
        ]
    )

    outcomes = signals.outcome_context.get("recent_outcomes") or []
    failures = signals.outcome_context.get("failed_outcomes") or []
    if outcomes or failures:
        for o in outcomes[:6]:
            parts.append(
                f"- SUCCESS: {o['title']}: {o.get('delta_summary', '')} "
                f"(score: {o.get('effectiveness_score', 'n/a')})"
            )
        for o in failures[:4]:
            parts.append(
                f"- FAILED/SKIPPED: {o['title']}: {o.get('delta_summary', o.get('reason', ''))}"
            )
        for s in (signals.outcome_context.get("effectiveness_scores") or [])[:5]:
            if s.get("sample_size", 0) >= 1:
                parts.append(
                    f"- {s['label']}: {s.get('success_rate')}% success (n={s['sample_size']})"
                )
    else:
        parts.append("No evaluated outcomes yet — do not claim past performance.")

    parts.extend(["", "=== 3. CONNECTED PLATFORM DATA ==="])
    if signals.has_connectors:
        for m in signals.connector_context.get("metrics", [])[:12]:
            parts.append(f"- {m['provider']}/{m['key']}: {m['value']}")
    else:
        parts.append("No synced platform metrics — do not cite social/ad platform stats.")

    # Phase 4 — normalized, computed marketing-analytics evidence. This is the
    # authoritative source for platform trends: the model may explain these
    # numbers but must never alter or invent them.
    if signals.analytics_signal is not None:
        parts.extend(["", signal_to_prompt_block(signals.analytics_signal)])

    parts.extend(["", "=== 4. CONTENT INTELLIGENCE ==="])
    if signals.has_content_intel:
        for line in signals.content_intelligence.get("insights", [])[:10]:
            parts.append(f"- {line}")
    else:
        parts.append("Insufficient content performance data — avoid format/platform claims.")

    parts.extend(["", "=== 5. LEAD INTELLIGENCE ==="])
    if signals.has_lead_intel:
        for line in signals.lead_context.get("insights", [])[:8]:
            parts.append(f"- {line}")
    else:
        parts.append("No lead activity — recommend pipeline setup, not outreach tactics.")

    parts.extend(["", "=== 6. INTERNAL ANALYTICS ==="])
    for s in signals.analytics_signals:
        parts.append(f"- {s}")

    parts.append(
        "\nEvery recommendation MUST cite data_sources_used from the signals above. "
        "If a signal category is empty, say so and lower confidence — never fill gaps with generic advice."
    )
    return "\n".join(parts)


def has_minimum_evidence(signals: IntelligenceSignals) -> bool:
    """Enough real data to generate non-generic recommendations."""
    if not signals.brain_complete:
        return False
    return (
        signals.activity_signals > 0
        or signals.has_outcomes
        or signals.has_connectors
        or signals.has_content_intel
        or signals.has_lead_intel
    )
