"""Unified signal gatherer — every recommendation must load these first."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

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
from aicmo.modules.onboarding.schemas import BusinessProfileResponse


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


async def gather_intelligence_signals(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    brand_id: uuid.UUID,
) -> IntelligenceSignals:
    """Load Business Brain → Outcomes → Connectors → Content → Leads → Analytics."""
    brain = load_business_brain(profile)
    _, setup_steps = brain_completeness(brain)

    outcome_ctx = await load_outcome_context(session, brand_id=brand_id)
    connector_ctx = await load_connector_context(session, brand_id=brand_id)
    content_ctx = await load_content_intelligence(session, brand_id=brand_id)
    lead_ctx = await load_lead_context(session, brand_id=brand_id)
    overview = await analytics_service.overview(session, brand_id=brand_id)
    analytics_signals = [
        f"Total leads: {overview.total_leads}",
        f"Leads (7d): {overview.leads_7d}",
        f"Leads (30d): {overview.leads_30d}",
        f"Hot leads: {overview.hot_leads}",
    ]
    if overview.conversion_rate > 0:
        analytics_signals.append(
            f"Landing page conversion: {overview.conversion_rate:.1%}"
        )

    data_sources: list[DataSourceRef] = [
        DataSourceRef(
            key="leads_7d", label="Leads (7 days)", value=str(overview.leads_7d)
        ),
        DataSourceRef(
            key="leads_30d", label="Leads (30 days)", value=str(overview.leads_30d)
        ),
        DataSourceRef(key="hot_leads", label="Hot leads", value=str(overview.hot_leads)),
    ]
    data_sources.extend(connector_ctx.get("data_sources", []))
    data_sources.extend(content_ctx.get("data_sources", []))
    data_sources.extend(lead_ctx.get("data_sources", []))

    activity_signals = sum(
        1
        for n in (overview.total_leads, overview.leads_7d, overview.leads_30d)
        if n > 0
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
    )


def signals_to_prompt_block(signals: IntelligenceSignals, *, confidence_cap: int) -> str:
    """Build LLM context in mandatory priority order."""
    parts = [
        f"CONFIDENCE CAP: Do not exceed {confidence_cap}. Never invent metrics.",
        "",
        "=== 1. BUSINESS BRAIN (required) ===",
        brain_to_prompt_block(signals.brain),
        "",
        "=== 2. HISTORICAL OUTCOMES (what worked / failed) ===",
    ]
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
