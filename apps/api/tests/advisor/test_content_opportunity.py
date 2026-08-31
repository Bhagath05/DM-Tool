"""Phase 6 — computed content insights become executable, human-approved
opportunities; the LLM never authors the numbers; no automatic publishing."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.advisor import intelligence
from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.advisor.signals import IntelligenceSignals
from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    Insight,
    MetricEvidence,
)
from aicmo.modules.opportunities.schemas import GeneratorHint
from aicmo.tenancy.context import TenantContext


def _content_insight(change_percent: float = 31.0, *, with_hint: bool = True) -> Insight:
    return Insight(
        id="content_format_outperforms:reel",
        severity="good",
        observation=(
            f"Your reel content is outperforming your recent median engagement by "
            f"{change_percent:.0f}% — 3 of 3 recent reels are above it."
        ),
        evidence=[
            MetricEvidence(
                metric="engagement_rate",
                label="reel engagement rate",
                platform="Instagram",
                current=0.10,
                previous=0.06,
                change_percent=change_percent,
                window="90d",
            )
        ],
        interpretation="Reels are resonating more than your typical post.",
        recommendation="Repeat this format — make more reel content.",
        reason="reel median above overall median",
        confidence=68,
        confidence_band="medium",
        expected_result="Higher average engagement if you keep leaning into reels.",
        impact_category="lead",
        window="90d",
        generator_hint=(
            {
                "target": "content",
                "format": "reel",
                "platform": "Instagram",
                "goal": "Repeat your winning reel format",
            }
            if with_hint
            else None
        ),
    )


def _signal(insight: Insight | None) -> AdvisorAnalyticsSignal:
    return AdvisorAnalyticsSignal(
        has_data=False,
        connected=True,
        data_sufficiency="none",
        window="7d",
        headline="hi",
        content_insights=[insight] if insight else [],
    )


def _ctx(signal: AdvisorAnalyticsSignal) -> IntelligenceSignals:
    return IntelligenceSignals(
        brain=BusinessBrain(industry="Cafe", business_type="Coffee", target_audience="Urban pros"),
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={"metrics": [], "has_data": False},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 1"],
        data_sources=[DataSourceRef(key="x", label="x", value="1")],
        has_connectors=False,
        activity_signals=1,
        analytics_signal=signal,
    )


# ---------------- pure conversion ----------------


def test_content_insight_becomes_executable_opportunity():
    opps = intelligence._content_opportunities(_ctx(_signal(_content_insight(31.0))), cap=70)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.kind == "content"
    # deep-links into a real generator (Creative Studio), pre-filled
    hint = GeneratorHint.model_validate(opp.generator_hint)
    assert hint.target == "content" and hint.format == "reel"
    # the computed number is preserved in the evidence carried to the UI
    assert any("+31% vs median" in ds.value for ds in opp.data_sources_used)


def test_insight_without_hint_is_not_executable():
    opps = intelligence._content_opportunities(
        _ctx(_signal(_content_insight(with_hint=False))), cap=70
    )
    assert opps == []


def test_opportunity_confidence_is_capped():
    opps = intelligence._content_opportunities(_ctx(_signal(_content_insight())), cap=50)
    assert opps[0].confidence <= 50


# ---------------- compose integration + evidence integrity ----------------


def _tenant() -> TenantContext:
    return TenantContext(
        user_id="u",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
    )


def _narrative(hero_obs: str):
    rec = intelligence._NarrativeRec(
        observation=hero_obs,
        root_cause="Distribution expanded this week for the brand.",
        recommended_action="Keep posting and sharpen hooks to lift engagement.",
        expected_impact="Higher engagement per unit of reach over two weeks.",
        confidence=60,
        data_sources_used=[DataSourceRef(key="reach", label="Reach", value="+10%")],
    )
    return intelligence._IntelligenceNarrative(
        daily_brief_what_happened="Reach grew steadily across the brand this week.",
        daily_brief_why="Posting cadence increased across channels.",
        daily_brief_confidence=60,
        hero=rec,
        content_opportunities=[],  # LLM proposes none — the content opp comes from computed evidence
        ad_opportunities=[],
        trend=None,
    )


class _FakeRouter:
    def __init__(self, narrative):
        self._n = narrative

    async def generate(self, **kw):
        return SimpleNamespace(data=self._n)


@pytest.mark.asyncio
async def test_compose_surfaces_executable_content_opportunity(monkeypatch):
    ctx = _ctx(_signal(_content_insight(31.0)))
    monkeypatch.setattr(intelligence, "gather_intelligence_signals", AsyncMock(return_value=ctx))
    # LLM prose invents a WRONG number; it must not reach the computed evidence.
    monkeypatch.setattr(
        intelligence,
        "get_llm_router",
        lambda: _FakeRouter(_narrative("Reels are up +99% (model's own wrong claim).")),
    )
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(advisor_intelligence_enabled=True, advisor_engine_enabled=False),
    )

    report = await intelligence.compose_intelligence(
        SimpleNamespace(), profile=SimpleNamespace(), tenant=_tenant()
    )

    content_opps = [o for o in report.content_opportunities if o.kind == "content"]
    assert any(
        GeneratorHint.model_validate(o.generator_hint).format == "reel" for o in content_opps
    )
    # the computed +31% survives; the LLM's +99% never enters the evidence
    reel_opp = next(o for o in content_opps if "reel" in o.recommended_action.lower())
    assert any("+31%" in ds.value for ds in reel_opp.data_sources_used)
    assert all("+99%" not in ds.value for ds in reel_opp.data_sources_used)


# ---------------- human approval required (no automatic publishing) ----------------


def test_publish_requires_human_approval_invariant():
    from aicmo.modules.publishing.queue_service import PUBLISHABLE_APPROVALS

    # A recommendation-driven post awaiting review ("pending") can NEVER be
    # auto-published: only already-approved or approval-not-required posts publish.
    assert "pending" not in PUBLISHABLE_APPROVALS
    assert "rejected" not in PUBLISHABLE_APPROVALS
    assert "approved" in PUBLISHABLE_APPROVALS
    assert "not_required" in PUBLISHABLE_APPROVALS
