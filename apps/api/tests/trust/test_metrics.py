"""Deterministic metric registry: correctness, NOT_COMPUTABLE, no NaN/Inf."""

from __future__ import annotations

import math

import pytest

from aicmo.modules.trust.contracts import ProposedMetric
from aicmo.modules.trust.enums import ReasonCode, SourceTier
from aicmo.modules.trust.metrics import compute_metric, is_known_metric


def _m(name: str, inputs: dict, tier: SourceTier = SourceTier.FIRST_PARTY_DATA) -> ProposedMetric:
    return ProposedMetric(name=name, inputs=inputs, source_tier=tier)


class TestCorrectCalculations:
    def test_ctr(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": 18, "impressions": 100}))
        assert r.computable and r.value == pytest.approx(18.0) and r.unit == "%"

    def test_conversion_rate(self) -> None:
        r = compute_metric(_m("conversion_rate", {"conversions": 7, "clicks": 100}))
        assert r.computable and r.value == pytest.approx(7.0)

    def test_roas(self) -> None:
        r = compute_metric(_m("roas", {"revenue": 450, "spend": 100}, SourceTier.VERIFIED_PROVIDER))
        assert r.computable and r.value == pytest.approx(4.5)

    def test_cac(self) -> None:
        r = compute_metric(_m("cac", {"spend": 800, "new_customers": 1}, SourceTier.VERIFIED_PROVIDER))
        assert r.computable and r.value == pytest.approx(800.0)

    def test_cpa(self) -> None:
        r = compute_metric(_m("cpa", {"spend": 120, "conversions": 1}, SourceTier.VERIFIED_PROVIDER))
        assert r.computable and r.value == pytest.approx(120.0)

    def test_percentage_change_positive(self) -> None:
        r = compute_metric(_m("percentage_change", {"current": 120, "baseline": 100}))
        assert r.computable and r.value == pytest.approx(20.0)

    def test_percentage_change_negative_baseline_uses_magnitude(self) -> None:
        r = compute_metric(_m("percentage_change", {"current": -50, "baseline": -100}))
        assert r.computable and r.value == pytest.approx(50.0)


class TestNotComputable:
    def test_zero_denominator_ctr(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": 5, "impressions": 0}))
        assert not r.computable and r.value is None
        assert r.reason_code is ReasonCode.NOT_COMPUTABLE

    def test_zero_spend_roas(self) -> None:
        r = compute_metric(_m("roas", {"revenue": 100, "spend": 0}, SourceTier.VERIFIED_PROVIDER))
        assert not r.computable and r.reason_code is ReasonCode.NOT_COMPUTABLE

    def test_missing_input(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": 5}))
        assert not r.computable and r.reason_code is ReasonCode.NOT_COMPUTABLE

    def test_none_input(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": 5, "impressions": None}))
        assert not r.computable and r.reason_code is ReasonCode.NOT_COMPUTABLE

    def test_negative_count_rejected(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": -5, "impressions": 100}))
        assert not r.computable

    def test_percentage_change_zero_baseline(self) -> None:
        r = compute_metric(_m("percentage_change", {"current": 10, "baseline": 0}))
        assert not r.computable and r.reason_code is ReasonCode.NOT_COMPUTABLE

    def test_unknown_metric_is_missing(self) -> None:
        r = compute_metric(_m("made_up_metric", {"x": 1}))
        assert not r.computable and r.reason_code is ReasonCode.MISSING_METRIC
        assert not is_known_metric("made_up_metric")


class TestNoNonFiniteEverEscapes:
    @pytest.mark.parametrize(
        "inputs",
        [
            {"clicks": float("inf"), "impressions": 100},
            {"clicks": float("nan"), "impressions": 100},
            {"clicks": 5, "impressions": float("inf")},
            {"clicks": 1e308, "impressions": 1e-308},  # overflow-prone ratio
        ],
    )
    def test_non_finite_inputs_never_produce_a_value(self, inputs) -> None:
        r = compute_metric(_m("ctr", inputs))
        assert r.value is None or math.isfinite(r.value)
        if r.value is None:
            assert not r.computable


class TestMonetarySourceGate:
    @pytest.mark.parametrize("metric,inputs", [
        ("spend", {"spend": 100}),
        ("revenue", {"revenue": 100}),
        ("roas", {"revenue": 100, "spend": 50}),
        ("cac", {"spend": 100, "new_customers": 2}),
        ("cpa", {"spend": 100, "conversions": 2}),
    ])
    @pytest.mark.parametrize("tier", [
        SourceTier.USER_PROVIDED, SourceTier.DERIVED_INTERNAL, SourceTier.RESEARCH,
        SourceTier.MODEL_INFERENCE, SourceTier.UNKNOWN,
    ])
    def test_monetary_requires_verified_or_first_party(self, metric, inputs, tier) -> None:
        r = compute_metric(_m(metric, inputs, tier))
        assert not r.computable
        assert r.reason_code is ReasonCode.UNVERIFIED_SOURCE

    @pytest.mark.parametrize("tier", [SourceTier.VERIFIED_PROVIDER, SourceTier.FIRST_PARTY_DATA])
    def test_monetary_allowed_for_verified_sources(self, tier) -> None:
        r = compute_metric(_m("roas", {"revenue": 100, "spend": 50}, tier))
        assert r.computable and r.value == pytest.approx(2.0)

    def test_nonmonetary_metric_allowed_for_any_source(self) -> None:
        r = compute_metric(_m("ctr", {"clicks": 5, "impressions": 100}, SourceTier.USER_PROVIDED))
        assert r.computable
