"""Recommendation validation: evidence for a claim is not evidence for an action."""

from __future__ import annotations

from aicmo.modules.trust.contracts import CandidateRecommendation
from aicmo.modules.trust.enums import (
    ConsequenceLevel,
    EvidenceBand,
    ReasonCode,
    RecommendationStatus,
    SourceTier,
)
from aicmo.modules.trust.recommendations import validate_recommendation


def _rec(**kw: object) -> CandidateRecommendation:
    base = CandidateRecommendation(
        statement="Do the thing",
        consequence_level=ConsequenceLevel.LOW,
        supporting_confidence=50,
        band=EvidenceBand.WEAK,
        has_supporting_evidence=True,
        bears_on_action=True,
        scope_match=True,
        contradicted=False,
        expected_effect="More leads",
        reversible=True,
        testable=True,
        source_tiers=[SourceTier.FIRST_PARTY_DATA],
    )
    return base.model_copy(update=kw) if kw else base


class TestDecisionIntelligenceGate:
    def test_evidence_not_bearing_on_action_is_insufficient(self) -> None:
        r = validate_recommendation(_rec(bears_on_action=False))
        assert r.status is RecommendationStatus.INSUFFICIENT_EVIDENCE
        assert ReasonCode.RECOMMENDATION_EXCEEDS_EVIDENCE in r.reasons

    def test_no_supporting_evidence_is_insufficient(self) -> None:
        r = validate_recommendation(_rec(has_supporting_evidence=False))
        assert r.status is RecommendationStatus.INSUFFICIENT_EVIDENCE


class TestContradiction:
    def test_contradicted_action_is_contradicted(self) -> None:
        r = validate_recommendation(_rec(contradicted=True, band=EvidenceBand.STRONG, supporting_confidence=90))
        assert r.status is RecommendationStatus.CONTRADICTED
        assert ReasonCode.CONFLICTING_EVIDENCE in r.reasons


class TestConsequenceBars:
    def test_low_supported(self) -> None:
        r = validate_recommendation(_rec(consequence_level=ConsequenceLevel.LOW, band=EvidenceBand.WEAK, supporting_confidence=45))
        assert r.status is RecommendationStatus.SUPPORTED
        assert r.requires_approval is False

    def test_low_under_bar_insufficient(self) -> None:
        r = validate_recommendation(_rec(consequence_level=ConsequenceLevel.LOW, supporting_confidence=30))
        assert r.status is RecommendationStatus.INSUFFICIENT_EVIDENCE

    def test_medium_requires_moderate_and_60(self) -> None:
        ok = validate_recommendation(_rec(consequence_level=ConsequenceLevel.MEDIUM, band=EvidenceBand.MODERATE, supporting_confidence=65))
        assert ok.status is RecommendationStatus.SUPPORTED
        assert ok.requires_approval is True
        weak = validate_recommendation(_rec(consequence_level=ConsequenceLevel.MEDIUM, band=EvidenceBand.WEAK, supporting_confidence=65))
        assert weak.status is RecommendationStatus.INSUFFICIENT_EVIDENCE

    def test_high_needs_strong_fresh_verified(self) -> None:
        ok = validate_recommendation(_rec(
            consequence_level=ConsequenceLevel.HIGH, band=EvidenceBand.STRONG,
            supporting_confidence=80, source_tiers=[SourceTier.VERIFIED_PROVIDER],
        ))
        assert ok.status is RecommendationStatus.SUPPORTED
        assert ok.requires_approval is True

    def test_high_underevidenced_is_review_not_dropped(self) -> None:
        r = validate_recommendation(_rec(
            consequence_level=ConsequenceLevel.HIGH, band=EvidenceBand.MODERATE,
            supporting_confidence=60, source_tiers=[SourceTier.VERIFIED_PROVIDER],
        ))
        assert r.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW
        assert r.requires_approval is True
        assert ReasonCode.HIGH_CONSEQUENCE_UNDER_EVIDENCED in r.reasons

    def test_high_without_verified_source_is_review(self) -> None:
        r = validate_recommendation(_rec(
            consequence_level=ConsequenceLevel.HIGH, band=EvidenceBand.STRONG,
            supporting_confidence=90, source_tiers=[SourceTier.USER_PROVIDED],
        ))
        assert r.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW
        assert r.requires_approval is True


class TestQualification:
    def test_caveats_qualify_a_supported_action(self) -> None:
        r = validate_recommendation(_rec(
            consequence_level=ConsequenceLevel.LOW, band=EvidenceBand.WEAK,
            supporting_confidence=45, testable=False,
        ))
        assert r.status is RecommendationStatus.QUALIFIED
        assert r.limitations

    def test_scope_mismatch_qualifies(self) -> None:
        r = validate_recommendation(_rec(scope_match=False, supporting_confidence=45))
        assert r.status is RecommendationStatus.QUALIFIED


class TestApprovalNeverLowered:
    def test_high_consequence_always_requires_approval(self) -> None:
        for band in EvidenceBand:
            r = validate_recommendation(_rec(
                consequence_level=ConsequenceLevel.HIGH, band=band,
                supporting_confidence=95, source_tiers=[SourceTier.VERIFIED_PROVIDER],
            ))
            assert r.requires_approval is True
