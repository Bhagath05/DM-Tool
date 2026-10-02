"""Server-derived confidence: worked examples, bounds, model-independence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aicmo.modules.trust.confidence import derive_confidence
from aicmo.modules.trust.enums import ClaimType, EvidenceBand

_FRESH = None  # no reference_time => treated as fully fresh


class TestWorkedExamples:
    """The binding examples from §7.4 of the architecture."""

    def test_fact_strong_caps_at_95(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.STRONG, claim_type=ClaimType.FACT,
            supporting_count=3, reference_time=_FRESH, llm_proposed=88,
        )
        assert f.applied_ceiling == 95
        assert f.derived == 95
        assert f.final == 95

    def test_observation_moderate_single_support_is_55(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.OBSERVATION,
            supporting_count=1, reference_time=_FRESH, llm_proposed=95,
        )
        assert f.raw == 55  # 40 base + 15 support, no consistency on single support
        assert f.final == 55

    def test_interpretation_moderate_single_support_is_55(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.INTERPRETATION,
            supporting_count=1, reference_time=_FRESH, llm_proposed=40,
        )
        assert f.applied_ceiling == 70  # min(75 band, 70 type)
        assert f.final == 55

    def test_hypothesis_weak_single_support_is_40(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.WEAK, claim_type=ClaimType.HYPOTHESIS,
            supporting_count=1, reference_time=_FRESH, llm_proposed=92,
        )
        assert f.raw == 40
        assert f.final == 40

    def test_hypothesis_weak_with_one_contradiction_is_20(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.WEAK, claim_type=ClaimType.HYPOTHESIS,
            supporting_count=1, contradiction_count=1, reference_time=_FRESH,
        )
        assert f.raw == 20
        assert f.final == 20


class TestGates:
    def test_insufficient_band_yields_zero(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.INSUFFICIENT, claim_type=ClaimType.OBSERVATION,
            supporting_count=3, reference_time=_FRESH,
        )
        assert f.final == 0
        assert f.derived == 0

    def test_zero_support_yields_zero(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.STRONG, claim_type=ClaimType.FACT,
            supporting_count=0, reference_time=_FRESH,
        )
        assert f.final == 0


class TestModelIndependence:
    """The LLM-proposed number is diagnostic only — never an input (I1, I14)."""

    @pytest.mark.parametrize("band", list(EvidenceBand))
    @pytest.mark.parametrize("claim_type", [ClaimType.FACT, ClaimType.OBSERVATION, ClaimType.HYPOTHESIS])
    @pytest.mark.parametrize("llm", [0, 10, 50, 92, 100, None])
    def test_llm_proposed_never_changes_final(self, band, claim_type, llm) -> None:
        base = derive_confidence(
            band=band, claim_type=claim_type, supporting_count=2,
            contradiction_count=0, reference_time=_FRESH, llm_proposed=None,
        )
        variant = derive_confidence(
            band=band, claim_type=claim_type, supporting_count=2,
            contradiction_count=0, reference_time=_FRESH, llm_proposed=llm,
        )
        assert base.final == variant.final
        assert base.derived == variant.derived

    def test_high_llm_cannot_raise_a_capped_value(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.OBSERVATION,
            supporting_count=1, reference_time=_FRESH, llm_proposed=92,
        )
        assert f.final == 55
        assert f.llm_proposed_diagnostic == 92

    def test_low_llm_cannot_drag_down_a_well_evidenced_value(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.STRONG, claim_type=ClaimType.FACT,
            supporting_count=3, reference_time=_FRESH, llm_proposed=5,
        )
        assert f.final == 95


class TestBoundsAndMonotonicity:
    def test_never_exceeds_applied_ceiling(self) -> None:
        for band in EvidenceBand:
            for ct in ClaimType:
                f = derive_confidence(
                    band=band, claim_type=ct, supporting_count=10,
                    experimental=True, consistent=True, reference_time=_FRESH,
                    recommendation_support_confidence=80,
                )
                assert 0 <= f.final <= 100
                if f.applied_ceiling:
                    assert f.final <= f.applied_ceiling

    def test_more_support_never_lowers_confidence(self) -> None:
        prev = -1
        for n in range(1, 6):
            f = derive_confidence(
                band=EvidenceBand.MODERATE, claim_type=ClaimType.OBSERVATION,
                supporting_count=n, reference_time=_FRESH,
            )
            assert f.final >= prev
            prev = f.final

    def test_more_contradictions_never_raises_confidence(self) -> None:
        prev = 101
        for c in range(0, 4):
            f = derive_confidence(
                band=EvidenceBand.STRONG, claim_type=ClaimType.OBSERVATION,
                supporting_count=3, contradiction_count=c, reference_time=_FRESH,
            )
            assert f.final <= prev
            prev = f.final


class TestFreshnessDecay:
    def test_stale_evidence_lowers_final_below_derived(self) -> None:
        old = datetime.now(UTC) - timedelta(days=365)
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.OBSERVATION,
            supporting_count=1, reference_time=old,
        )
        assert f.derived == 55
        assert f.final < f.derived
        assert f.final > 0  # decays to a floor, never to zero for held evidence


class TestRecommendationTypeCeiling:
    def test_recommendation_capped_by_weakest_support(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.RECOMMENDATION,
            supporting_count=2, reference_time=_FRESH,
            recommendation_support_confidence=30,
        )
        assert f.claim_ceiling == 30
        assert f.final <= 30

    def test_recommendation_without_support_confidence_gates_low(self) -> None:
        f = derive_confidence(
            band=EvidenceBand.MODERATE, claim_type=ClaimType.RECOMMENDATION,
            supporting_count=2, reference_time=_FRESH,
            recommendation_support_confidence=None,
        )
        assert f.final == 0
