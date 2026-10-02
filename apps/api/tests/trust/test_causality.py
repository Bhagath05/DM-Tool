"""Causal gate: correlation is never promoted to causation without a design."""

from __future__ import annotations

from aicmo.modules.trust.causality import (
    CURRENT_MAX_CAPABILITY,
    assess_causality,
    looks_causal,
)
from aicmo.modules.trust.enums import CausalLevel, ReasonCode, SourceTier


class TestCausalDetection:
    def test_detects_causal_phrasing(self) -> None:
        assert looks_causal("The new video caused a spike in signups")
        assert looks_causal("Signups rose because of the discount")
        assert looks_causal("The campaign drove more leads")

    def test_non_causal_phrasing_not_flagged(self) -> None:
        assert not looks_causal("CTR was 3.2% last week")
        assert not looks_causal("Signups rose alongside the new video")

    def test_detection_only_tightens_never_loosens(self) -> None:
        # Caller says not causal, but wording is clearly causal => still gated.
        a = assess_causality(
            statement="X caused Y", evidence_level=CausalLevel.OBSERVATIONAL,
            is_causal_candidate=False,
        )
        assert a.is_causal_candidate is True
        assert a.downgraded is True


class TestDowngradeLadder:
    def test_observational_causal_is_downgraded(self) -> None:
        a = assess_causality(
            statement="The video caused more signups",
            evidence_level=CausalLevel.OBSERVATIONAL,
            source_tiers=[SourceTier.FIRST_PARTY_DATA],
        )
        assert not a.permitted and a.downgraded
        assert a.reason_code is ReasonCode.UNSUPPORTED_CAUSAL_CLAIM
        assert a.suggested_statement

    def test_quasi_experimental_is_scope_exceeded(self) -> None:
        a = assess_causality(
            statement="The change caused the lift",
            evidence_level=CausalLevel.QUASI_EXPERIMENTAL,
            source_tiers=[SourceTier.FIRST_PARTY_DATA],
        )
        assert not a.permitted and a.downgraded
        assert a.reason_code is ReasonCode.CAUSAL_SCOPE_EXCEEDED

    def test_controlled_experiment_permits_causal(self) -> None:
        a = assess_causality(
            statement="The treatment caused the improvement",
            evidence_level=CausalLevel.CONTROLLED_EXPERIMENT,
            source_tiers=[SourceTier.FIRST_PARTY_DATA],
        )
        assert a.permitted and not a.downgraded

    def test_randomized_permits_causal(self) -> None:
        a = assess_causality(
            statement="The treatment caused the improvement",
            evidence_level=CausalLevel.RANDOMIZED,
            source_tiers=[SourceTier.VERIFIED_PROVIDER],
        )
        assert a.permitted and not a.downgraded


class TestGroundingAndCapability:
    def test_model_inference_only_cannot_back_causal(self) -> None:
        a = assess_causality(
            statement="The ad caused the sales lift",
            evidence_level=CausalLevel.RANDOMIZED,  # even a strong claimed level
            source_tiers=[SourceTier.MODEL_INFERENCE],
        )
        assert not a.permitted and a.downgraded
        assert a.reason_code is ReasonCode.UNSUPPORTED_CAUSAL_CLAIM

    def test_permitted_level_beyond_capability_carries_disclosure(self) -> None:
        a = assess_causality(
            statement="The treatment caused the change",
            evidence_level=CausalLevel.RANDOMIZED,
            source_tiers=[SourceTier.FIRST_PARTY_DATA],
        )
        assert a.permitted
        assert a.disclosure and CURRENT_MAX_CAPABILITY.value in a.disclosure

    def test_non_causal_statement_passes_through(self) -> None:
        a = assess_causality(
            statement="Signups rose alongside the new video",
            evidence_level=CausalLevel.OBSERVATIONAL,
        )
        assert not a.is_causal_candidate and a.permitted and not a.downgraded
