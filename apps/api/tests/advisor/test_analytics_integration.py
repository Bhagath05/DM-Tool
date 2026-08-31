"""Phase 4 — marketing-analytics → advisor integration.

Proves the one-directional feed reaches the advisor prompt, is attached to the
report unchanged, and that the LLM can never alter the computed evidence.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.advisor import intelligence
from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.advisor.signals import IntelligenceSignals, signals_to_prompt_block
from aicmo.modules.analytics.schemas import OverviewKpis
from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    AdvisorPlatformEvidence,
    Insight,
    MetricEvidence,
)
from aicmo.tenancy.context import TenantContext

# ---------------- fixtures / builders ----------------


def _reach_evidence(change_percent: float = 24.0) -> MetricEvidence:
    return MetricEvidence(
        metric=normalize.REACH,
        label="Reach (28 days)",
        provider="instagram_organic",
        platform="Instagram",
        current=1240,
        previous=1000,
        absolute_change=240,
        change_percent=change_percent,
        window="7d",
    )


def _signal(change_percent: float = 24.0) -> AdvisorAnalyticsSignal:
    ev = _reach_evidence(change_percent)
    insight = Insight(
        id="reach_up_engagement_flat:instagram_organic:reach",
        severity="attention",
        observation=f"Instagram reach is up {change_percent:.0f}% while engagement stayed flat.",
        evidence=[ev],
        interpretation="Distribution outran interaction.",
        recommendation="Test stronger hooks and CTAs in your next 3 posts.",
        reason="reach up, engagement flat",
        confidence=68,
        confidence_band="medium",
        expected_result="Higher engagement per unit of reach.",
        impact_category="lead",
        window="7d",
    )
    return AdvisorAnalyticsSignal(
        has_data=True,
        connected=True,
        data_sufficiency="weekly",
        window="7d",
        headline=f"Instagram reach is up {change_percent:.0f}% this week.",
        platforms=[
            AdvisorPlatformEvidence(
                provider_slug="instagram_organic", platform="Instagram", metrics=[ev]
            )
        ],
        insights=[insight],
        evidence=[ev],
        confidence_band="medium",
    )


def _ctx(analytics_signal: AdvisorAnalyticsSignal | None) -> IntelligenceSignals:
    brain = BusinessBrain(
        industry="Cafe",
        business_type="Coffee shop",
        target_audience="Urban professionals who want specialty coffee",
    )
    return IntelligenceSignals(
        brain=brain,
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={"metrics": [], "has_data": True},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 3"],
        data_sources=[DataSourceRef(key="leads_7d", label="Leads (7 days)", value="3")],
        has_outcomes=False,
        has_connectors=True,
        has_content_intel=False,
        has_lead_intel=False,
        activity_signals=1,
        analytics_signal=analytics_signal,
    )


def _narrative(hero_observation: str):
    rec = intelligence._NarrativeRec(
        observation=hero_observation,
        root_cause="Increased posting cadence expanded distribution this week.",
        recommended_action="Keep posting and add stronger hooks to lift engagement.",
        expected_impact="Higher engagement per unit of reach over the next two weeks.",
        confidence=65,
        data_sources_used=[DataSourceRef(key="reach", label="Reach", value="+24%")],
    )
    return intelligence._IntelligenceNarrative(
        daily_brief_what_happened="Reach grew strongly across Instagram this week.",
        daily_brief_why="A higher posting cadence expanded distribution.",
        daily_brief_confidence=60,
        hero=rec,
        content_opportunities=[],
        ad_opportunities=[],
        trend=None,
    )


class _FakeRouter:
    def __init__(self, narrative=None, raise_exc=False):
        self.narrative = narrative
        self.raise_exc = raise_exc
        self.captured_messages = None

    async def generate(self, *, response_schema, system, messages, **kw):
        self.captured_messages = messages
        if self.raise_exc:
            raise RuntimeError("llm unavailable")
        return SimpleNamespace(data=self.narrative)


def _tenant() -> TenantContext:
    return TenantContext(
        user_id="u",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
    )


def _overview() -> OverviewKpis:
    return OverviewKpis(
        total_leads=3,
        leads_7d=1,
        leads_30d=3,
        hot_leads=1,
        landing_pages_published=1,
        total_views=10,
        total_submissions=2,
        conversion_rate=0.2,
        top_landing_page_title=None,
        top_landing_page_slug=None,
        top_landing_page_submissions=0,
    )


def _patch_settings(monkeypatch):
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(advisor_intelligence_enabled=True, advisor_engine_enabled=False),
    )


# ---------------- prompt-block wiring (pure) ----------------


def test_prompt_block_includes_marketing_signal():
    block = signals_to_prompt_block(_ctx(_signal(24.0)), confidence_cap=70)
    assert "MARKETING ANALYTICS SIGNAL" in block
    assert "+24%" in block
    assert "Instagram" in block


def test_prompt_block_without_signal_does_not_crash():
    block = signals_to_prompt_block(_ctx(None), confidence_cap=70)
    assert "MARKETING ANALYTICS SIGNAL" not in block
    assert "BUSINESS BRAIN" in block  # the rest of the prompt still builds


# ---------------- compose_intelligence attaches + preserves the signal ----------------


@pytest.mark.asyncio
async def test_compose_attaches_computed_signal(monkeypatch):
    signal = _signal(24.0)
    monkeypatch.setattr(
        intelligence, "gather_intelligence_signals", AsyncMock(return_value=_ctx(signal))
    )
    monkeypatch.setattr(
        intelligence, "get_llm_router", lambda: _FakeRouter(_narrative("Reach up nicely."))
    )
    _patch_settings(monkeypatch)

    report = await intelligence.compose_intelligence(
        SimpleNamespace(), profile=SimpleNamespace(), tenant=_tenant()
    )
    assert report.marketing_signal is not None
    assert report.marketing_signal.evidence[0].change_percent == 24.0


@pytest.mark.asyncio
async def test_llm_cannot_alter_computed_evidence(monkeypatch):
    """CRITICAL: analytics computed reach +24%. Even when the LLM's prose claims
    +42%, the attached computed evidence must remain +24% and the prompt the LLM
    received must contain +24% (never +42%)."""
    signal = _signal(24.0)
    fake_router = _FakeRouter(
        _narrative("Instagram reach exploded +42% this week (model's own wrong claim).")
    )
    monkeypatch.setattr(
        intelligence, "gather_intelligence_signals", AsyncMock(return_value=_ctx(signal))
    )
    monkeypatch.setattr(intelligence, "get_llm_router", lambda: fake_router)
    _patch_settings(monkeypatch)

    report = await intelligence.compose_intelligence(
        SimpleNamespace(), profile=SimpleNamespace(), tenant=_tenant()
    )

    # 1. computed evidence is authoritative and unchanged by the LLM
    reach = [e for e in report.marketing_signal.evidence if e.metric == normalize.REACH]
    assert reach and reach[0].change_percent == 24.0
    assert all(e.change_percent != 42.0 for e in report.marketing_signal.evidence)

    # 2. the LLM was only ever fed the computed +24% — never a fabricated +42%
    prompt = fake_router.captured_messages[0].content
    assert "+24%" in prompt
    assert "42%" not in prompt


@pytest.mark.asyncio
async def test_llm_failure_still_attaches_signal(monkeypatch):
    """When the LLM fails, the deterministic report must still carry the
    computed signal — the advisor stays honest and useful."""
    signal = _signal(24.0)
    monkeypatch.setattr(
        intelligence, "gather_intelligence_signals", AsyncMock(return_value=_ctx(signal))
    )
    monkeypatch.setattr(intelligence, "get_llm_router", lambda: _FakeRouter(raise_exc=True))
    monkeypatch.setattr(
        intelligence.analytics_service, "overview", AsyncMock(return_value=_overview())
    )
    _patch_settings(monkeypatch)

    report = await intelligence.compose_intelligence(
        SimpleNamespace(), profile=SimpleNamespace(), tenant=_tenant()
    )
    assert report.ready is True  # deterministic fallback
    assert report.marketing_signal is not None
    assert report.marketing_signal.evidence[0].change_percent == 24.0


@pytest.mark.asyncio
async def test_advisor_works_with_no_analytics_data(monkeypatch):
    """No analytics signal at all → advisor still produces a report, no crash."""
    monkeypatch.setattr(
        intelligence, "gather_intelligence_signals", AsyncMock(return_value=_ctx(None))
    )
    monkeypatch.setattr(
        intelligence, "get_llm_router", lambda: _FakeRouter(_narrative("Steady week."))
    )
    _patch_settings(monkeypatch)

    report = await intelligence.compose_intelligence(
        SimpleNamespace(), profile=SimpleNamespace(), tenant=_tenant()
    )
    assert report.ready is True
    assert report.marketing_signal is None
