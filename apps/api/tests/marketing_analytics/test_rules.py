"""Deterministic insight rules + evidence integrity."""

from __future__ import annotations

from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.rules import (
    MetricState,
    confidence_band,
    generate_insights,
)
from aicmo.modules.marketing_analytics.sufficiency import Sufficiency, SufficiencyLevel
from aicmo.modules.marketing_analytics.timeseries import FLAT_BAND_PCT, Comparison

WEEKLY = Sufficiency(level=SufficiencyLevel.WEEKLY, days_covered=10, observations=40)
SHORT = Sufficiency(level=SufficiencyLevel.SHORT_TERM, days_covered=3, observations=6)


def _comp(current: float, previous: float, window_days: int = 7) -> Comparison:
    abs_change = current - previous
    pct = round(abs_change / abs(previous) * 100, 1) if previous != 0 else None
    if pct is not None:
        trend = "flat" if abs(pct) < FLAT_BAND_PCT else ("up" if pct > 0 else "down")
    else:
        trend = "flat" if abs_change == 0 else ("up" if abs_change > 0 else "down")
    return Comparison(
        current=current,
        previous=previous,
        absolute_change=abs_change,
        change_percent=pct,
        trend=trend,
        window_days=window_days,
    )


def _insufficient() -> Comparison:
    return Comparison(None, None, None, None, "insufficient", window_days=7)


def _state(
    provider: str,
    canonical: str,
    label: str,
    current: float,
    comparison: Comparison,
    *,
    kind: str = "rolling",
    comparable: bool = True,
) -> MetricState:
    return MetricState(
        provider_slug=provider,
        platform=normalize.provider_label(provider),
        canonical=canonical,
        label=label,
        kind=kind,
        unit="count",
        comparable=comparable,
        current=current,
        comparison=comparison,
    )


# ---------------- individual rules ----------------


def test_reach_up_engagement_flat_flags_attention():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1400, _comp(1400, 1000)),
        _state(
            "instagram_organic",
            normalize.ENGAGEMENT_RATE,
            "Engagement rate",
            0.051,
            _comp(0.051, 0.050),
            kind="rate",
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    hit = [i for i in out if i.id.startswith("reach_up_engagement_flat")]
    assert len(hit) == 1
    assert hit[0].severity == "attention"
    # evidence carries BOTH the reach and the engagement numbers it reasoned from
    metrics = {e.metric for e in hit[0].evidence}
    assert normalize.REACH in metrics and normalize.ENGAGEMENT_RATE in metrics
    assert "hook" in hit[0].recommendation.lower() or "cta" in hit[0].recommendation.lower()


def test_engagement_up_reach_stable_is_good_news():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1010, _comp(1010, 1000)),
        _state(
            "instagram_organic",
            normalize.ENGAGEMENT_RATE,
            "Engagement rate",
            0.065,
            _comp(0.065, 0.050),
            kind="rate",
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    hit = [i for i in out if i.id.startswith("engagement_up_reach_stable")]
    assert len(hit) == 1 and hit[0].severity == "good"


def test_audience_growth_is_good_news():
    states = [
        _state("youtube", normalize.AUDIENCE, "Subscribers", 1200, _comp(1200, 1000), kind="level")
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    hit = [i for i in out if i.id.startswith("audience_growth")]
    assert len(hit) == 1 and hit[0].severity == "good"
    assert hit[0].impact_category == "customer"


def test_core_decline_flags_attention():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 700, _comp(700, 1000))
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    hit = [i for i in out if i.id.startswith("core_decline")]
    assert len(hit) == 1 and hit[0].severity == "attention"


def test_cross_platform_leader_recommends_allocation():
    states = [
        _state("youtube", normalize.AUDIENCE, "Subscribers", 5000, _comp(5000, 4900), kind="level"),
        _state(
            "linkedin_organic",
            normalize.AUDIENCE,
            "Followers",
            1000,
            _comp(1000, 990),
            kind="level",
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    hit = [i for i in out if i.id.startswith("cross_platform_leader")]
    assert len(hit) == 1
    assert hit[0].severity == "neutral"
    assert "YouTube" in hit[0].recommendation


def test_no_cross_platform_leader_when_margin_is_small():
    states = [
        _state("youtube", normalize.AUDIENCE, "Subscribers", 1100, _comp(1100, 1090), kind="level"),
        _state(
            "linkedin_organic",
            normalize.AUDIENCE,
            "Followers",
            1000,
            _comp(1000, 990),
            kind="level",
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert not [i for i in out if i.id.startswith("cross_platform_leader")]


def test_all_platforms_declining_fires_once():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 700, _comp(700, 1000)),
        _state(
            "facebook_pages", normalize.IMPRESSIONS, "Impressions (28 days)", 800, _comp(800, 1200)
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert [i for i in out if i.id.startswith("all_platforms_decline")]


# ---------------- gating + integrity ----------------


def test_no_insights_when_data_insufficient():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1400, _comp(1400, 1000)),
        _state(
            "instagram_organic",
            normalize.ENGAGEMENT_RATE,
            "Engagement rate",
            0.051,
            _comp(0.051, 0.050),
            kind="rate",
        ),
    ]
    assert generate_insights(states, sufficiency=SHORT, window_days=7) == []


def test_no_insights_on_insufficient_comparisons():
    """A metric whose comparison is 'insufficient' must not produce a claim."""
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1400, _insufficient()),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert out == []


def test_flat_everything_produces_no_working_or_attention():
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1010, _comp(1010, 1000)),
        _state(
            "instagram_organic",
            normalize.ENGAGEMENT_RATE,
            "Engagement rate",
            0.0505,
            _comp(0.0505, 0.050),
            kind="rate",
        ),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert all(i.severity == "neutral" for i in out)  # no fabricated wins/problems


def test_evidence_only_cites_metrics_that_exist():
    """The core anti-fabrication guarantee: every evidence metric an insight
    cites must be a metric actually present in the input states."""
    states = [
        _state("instagram_organic", normalize.REACH, "Reach (28 days)", 1400, _comp(1400, 1000)),
        _state(
            "instagram_organic",
            normalize.ENGAGEMENT_RATE,
            "Engagement rate",
            0.051,
            _comp(0.051, 0.050),
            kind="rate",
        ),
        _state("youtube", normalize.AUDIENCE, "Subscribers", 1200, _comp(1200, 1000), kind="level"),
    ]
    present = {(s.provider_slug, s.canonical) for s in states}
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert out  # sanity: something fired
    for insight in out:
        for e in insight.evidence:
            assert (e.provider, e.metric) in present, f"fabricated evidence: {e}"


def test_confidence_never_exceeds_sufficiency_cap():
    states = [
        _state("youtube", normalize.AUDIENCE, "Subscribers", 1300, _comp(1300, 1000), kind="level"),
    ]
    out = generate_insights(states, sufficiency=WEEKLY, window_days=7)
    assert out
    for i in out:
        assert i.confidence <= 70  # WEEKLY cap
        assert i.confidence_band == confidence_band(i.confidence)


def test_confidence_band_thresholds():
    assert confidence_band(85) == "high"
    assert confidence_band(70) == "medium"
    assert confidence_band(45) == "low"
    assert confidence_band(30) == "speculative"
