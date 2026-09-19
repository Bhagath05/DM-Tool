"""Pure-logic tests for the AI-vs-human creative evaluator.

Deterministic, no DB, no LLM, no provider — proves the verdict logic, the
insufficient/invalid-comparison guards, the never-invent-a-metric rule, the
trend diagnosis, and the confidence bounds. These cover the evidence-engine
half of the required regression matrix; the governance/tenant/audit half lives
in tests/advisor/test_creative_evaluation_service.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aicmo.modules.marketing_analytics.creative_evaluation import (
    CONFIDENCE_CAP,
    CreativeSample,
    Provenance,
    TrendDirection,
    Verdict,
    diagnose_trend,
    evaluate_ai_vs_human,
)
from aicmo.modules.marketing_analytics.timeseries import Observation


def _s(prov: Provenance, *, platform="instagram", fmt="reel", spend=None, audience=None, **metrics):
    return CreativeSample(
        provenance=prov,
        metrics=dict(metrics),
        platform=platform,
        fmt=fmt,
        spend=spend,
        audience_size=audience,
    )


def _cohort(prov, n, **metrics):
    return [_s(prov, **metrics) for _ in range(n)]


# --- 1. insufficient evidence ---
def test_insufficient_when_too_few_samples():
    samples = _cohort(Provenance.AI, 2, views=800) + _cohort(Provenance.HUMAN, 5, views=1200)
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert out.confidence == 0
    assert out.ai_sample_size == 2 and out.human_sample_size == 5


def test_insufficient_when_no_shared_metric():
    samples = _cohort(Provenance.AI, 3, views=800) + _cohort(Provenance.HUMAN, 3, ctr=0.02)
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert (
        any(
            "shared metric" in lim.lower() or "not measured" in ev.lower()
            for lim in out.limitations
            for ev in out.evidence
        )
        or out.metric_deltas == []
    )


# --- 2. AI outperforming ---
def test_ai_outperforming():
    samples = _cohort(Provenance.AI, 3, views=1300, engagement_rate=0.039) + _cohort(
        Provenance.HUMAN, 3, views=1000, engagement_rate=0.030
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.AI_OUTPERFORMING
    assert 0 < out.confidence <= CONFIDENCE_CAP


# --- 3. AI underperforming (human better, not decisive) ---
def test_ai_underperforming():
    samples = _cohort(Provenance.AI, 3, views=800, engagement_rate=0.020) + _cohort(
        Provenance.HUMAN, 3, views=1200, engagement_rate=0.030
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.AI_UNDERPERFORMING
    assert out.ai_is_underperforming is True
    # every delta must be grounded in the two cohorts, not invented
    assert {d.metric for d in out.metric_deltas} == {"views", "engagement_rate"}


# --- 4. human outperforming (decisive: >=3 metrics, all large) ---
def test_human_outperforming_decisive():
    samples = _cohort(
        Provenance.AI, 4, views=600, engagement_rate=0.018, ctr=0.008, watch_time_seconds=5
    ) + _cohort(
        Provenance.HUMAN, 4, views=1200, engagement_rate=0.036, ctr=0.016, watch_time_seconds=11
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.HUMAN_OUTPERFORMING
    assert out.ai_is_underperforming is True


# --- 5. no significant difference ---
def test_no_significant_difference():
    samples = _cohort(Provenance.AI, 3, views=1000, engagement_rate=0.030) + _cohort(
        Provenance.HUMAN, 3, views=1030, engagement_rate=0.031
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.NO_SIGNIFICANT_DIFFERENCE


# --- 6. invalid comparisons ---
def test_invalid_comparison_different_platforms():
    samples = _cohort(Provenance.AI, 3, platform="tiktok", views=1500) + _cohort(
        Provenance.HUMAN, 3, platform="instagram", views=1000
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("different platforms" in lim for lim in out.limitations)


def test_invalid_comparison_spend_gap():
    samples = _cohort(Provenance.AI, 3, spend=1000.0, views=1500) + _cohort(
        Provenance.HUMAN, 3, spend=50.0, views=1000
    )
    out = evaluate_ai_vs_human(samples)
    assert out.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("spend differs" in lim.lower() for lim in out.limitations)


# --- 7 & 8. declining revenue / declining views (trend) ---
def _obs_series(values: list[float]) -> list[Observation]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Observation(value=v, observed_at=base + timedelta(days=i)) for i, v in enumerate(values)
    ]


def test_declining_revenue_trend():
    # 10 distinct days, second half clearly lower
    series = _obs_series([1000, 980, 1010, 990, 1000, 700, 680, 650, 660, 640])
    assert diagnose_trend(series, metric_label="attributed revenue") is TrendDirection.FALLING


def test_declining_views_trend():
    series = _obs_series([500, 510, 505, 495, 500, 300, 290, 280, 285, 270])
    assert diagnose_trend(series, metric_label="views") is TrendDirection.FALLING


def test_trend_insufficient_on_two_days():
    series = _obs_series([1000, 400])  # only 2 days — cannot claim a trend
    assert diagnose_trend(series, metric_label="views") is TrendDirection.INSUFFICIENT


# --- 9. fabricated / missing metrics ---
def test_missing_metrics_are_reported_never_invented():
    # only views present — revenue/conversions/roas/cac must NOT be fabricated
    samples = _cohort(Provenance.AI, 3, views=800) + _cohort(Provenance.HUMAN, 3, views=1200)
    out = evaluate_ai_vs_human(samples)
    compared = {d.metric for d in out.metric_deltas}
    assert compared == {"views"}
    assert not any(d.metric in {"revenue", "conversions", "roas", "cac"} for d in out.metric_deltas)
    assert any("attributed revenue" in lim for lim in out.limitations)


def test_available_revenue_is_used_when_present():
    # When per-creative revenue IS present on both cohorts it must be compared
    # (not ignored) and drive the verdict — and NOT reported as a limitation.
    samples = _cohort(Provenance.AI, 3, views=1000, revenue=40.0) + _cohort(
        Provenance.HUMAN, 3, views=1000, revenue=120.0
    )
    out = evaluate_ai_vs_human(samples)
    metrics = {d.metric for d in out.metric_deltas}
    assert "revenue" in metrics
    rev = next(d for d in out.metric_deltas if d.metric == "revenue")
    assert rev.significant and not rev.ai_better  # human revenue clearly higher
    assert not any("attributed revenue" in lim for lim in out.limitations)
    assert out.verdict in (Verdict.AI_UNDERPERFORMING, Verdict.HUMAN_OUTPERFORMING)


def test_unknown_metric_key_is_ignored():
    samples = _cohort(Provenance.AI, 3, views=1300, made_up_metric=999999) + _cohort(
        Provenance.HUMAN, 3, views=1000, made_up_metric=1
    )
    out = evaluate_ai_vs_human(samples)
    assert all(d.metric != "made_up_metric" for d in out.metric_deltas)


# --- 10. confidence bounds ---
def test_confidence_never_exceeds_cap_and_insufficient_is_zero():
    strong = _cohort(Provenance.AI, 20, views=600, engagement_rate=0.018, ctr=0.008) + _cohort(
        Provenance.HUMAN, 20, views=1400, engagement_rate=0.040, ctr=0.020
    )
    out = evaluate_ai_vs_human(strong)
    assert out.confidence <= CONFIDENCE_CAP
    assert out.confidence < 100  # a data verdict is never fully certain
    insufficient = evaluate_ai_vs_human(_cohort(Provenance.AI, 1, views=1))
    assert insufficient.confidence == 0


# --- 11. unknown provenance excluded ---
def test_unknown_provenance_excluded_and_flagged():
    samples = (
        _cohort(Provenance.AI, 3, views=1300)
        + _cohort(Provenance.HUMAN, 3, views=1000)
        + _cohort(Provenance.UNKNOWN, 4, views=999)
    )
    out = evaluate_ai_vs_human(samples)
    assert out.unknown_sample_size == 4
    assert any("unknown provenance" in lim.lower() for lim in out.limitations)
