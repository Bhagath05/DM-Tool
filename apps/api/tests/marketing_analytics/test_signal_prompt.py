"""Phase 4 — signal → LLM prompt block (computed-only, never fabricated)."""

from __future__ import annotations

from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    AdvisorPlatformEvidence,
    Insight,
    MetricEvidence,
)
from aicmo.modules.marketing_analytics.signal_prompt import signal_to_prompt_block


def _reach_ev(change_percent: float | None, current: float = 1240, previous: float = 1000):
    return MetricEvidence(
        metric=normalize.REACH,
        label="Reach (28 days)",
        provider="instagram_organic",
        platform="Instagram",
        current=current,
        previous=previous,
        absolute_change=current - previous,
        change_percent=change_percent,
        window="7d",
    )


def _signal(evidence, *, has_data=True, empty_message=None, empty_reason=None, insights=None):
    return AdvisorAnalyticsSignal(
        has_data=has_data,
        connected=True,
        data_sufficiency="weekly",
        window="7d",
        headline="Instagram reach is up 24% this week.",
        empty_reason=empty_reason,
        empty_message=empty_message,
        platforms=[
            AdvisorPlatformEvidence(
                provider_slug="instagram_organic", platform="Instagram", metrics=evidence
            )
        ]
        if evidence
        else [],
        insights=insights or [],
        evidence=[e for e in evidence if e.change_percent is not None],
    )


def test_prompt_contains_computed_number_and_guardrail():
    block = signal_to_prompt_block(_signal([_reach_ev(24.0)]))
    assert "+24%" in block
    assert "Instagram" in block
    # the hard instruction that the model must not alter/invent numbers
    assert "never" in block.lower() and "invent" in block.lower()


def test_prompt_never_emits_an_unsupported_value():
    """CRITICAL: if analytics computed +24%, the prompt must carry +24% and must
    NOT contain a different fabricated figure like +42%."""
    block = signal_to_prompt_block(_signal([_reach_ev(24.0)]))
    assert "24%" in block
    assert "42%" not in block
    assert "42" not in block


def test_prompt_empty_state_forbids_trend_claims():
    sig = _signal(
        [],
        has_data=False,
        empty_reason="no_connection",
        empty_message="Connect a marketing account to start receiving performance insights.",
    )
    block = signal_to_prompt_block(sig)
    assert "Connect a marketing account" in block
    assert "Do NOT claim any account-level trend" in block


def test_prompt_short_history_forbids_weekly_trend():
    ev = _reach_ev(None)  # no comparison yet
    sig = _signal(
        [ev],
        has_data=True,
        empty_reason="short_history",
        empty_message="We're still collecting data. Short-term observations are available, but reliable weekly trends aren't ready yet.",
    )
    block = signal_to_prompt_block(sig)
    assert "do NOT claim week-over-week" in block
    # a metric with no baseline must be shown as a level, not a trend
    assert "no prior-period baseline yet" in block


def test_prompt_includes_computed_insights_for_rephrasing():
    insight = Insight(
        id="reach_up_engagement_flat:instagram_organic:reach",
        severity="attention",
        observation="Instagram reach is up 24% while engagement stayed flat.",
        evidence=[_reach_ev(24.0)],
        interpretation="Distribution outran interaction.",
        recommendation="Test stronger hooks and CTAs in your next 3 posts.",
        reason="reach +24%, engagement flat",
        confidence=68,
        confidence_band="medium",
        expected_result="Higher engagement per unit of reach.",
        impact_category="lead",
        window="7d",
    )
    block = signal_to_prompt_block(_signal([_reach_ev(24.0)], insights=[insight]))
    assert "rephrase, not renumber" in block
    assert "Test stronger hooks" in block
