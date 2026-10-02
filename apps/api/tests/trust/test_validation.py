"""End-to-end Trust Layer orchestration: typing, verdicts, downgrades."""

from __future__ import annotations

from aicmo.modules.trust.contracts import (
    CandidateClaim,
    CandidateRecommendation,
    EvidenceRef,
    ProposedMetric,
    TrustInput,
)
from aicmo.modules.trust.enums import (
    CausalLevel,
    ClaimStatus,
    ClaimType,
    ConsequenceLevel,
    EvidenceBand,
    EvidenceStatus,
    RecommendationStatus,
    SourceTier,
    TrustVerdict,
)
from aicmo.modules.trust.validation import assess_band, validate_trust


def _ev(eid: str, *, supports: bool = True, tier: SourceTier = SourceTier.FIRST_PARTY_DATA) -> EvidenceRef:
    return EvidenceRef(evidence_id=eid, source_tier=tier, supports=supports)


class TestAssessBand:
    def test_no_support_is_insufficient(self) -> None:
        assert assess_band(supporting_count=0, grounding_source_count=0,
                           has_verified_source=False, contradiction_count=0,
                           consistent=True) is EvidenceBand.INSUFFICIENT

    def test_verified_multi_support_is_strong(self) -> None:
        assert assess_band(supporting_count=3, grounding_source_count=3,
                           has_verified_source=True, contradiction_count=0,
                           consistent=True) is EvidenceBand.STRONG

    def test_two_contradictions_force_weak(self) -> None:
        assert assess_band(supporting_count=3, grounding_source_count=3,
                           has_verified_source=True, contradiction_count=2,
                           consistent=True) is EvidenceBand.WEAK


class TestCleanFact:
    def test_verified_computed_metric_is_fact_and_accepted(self) -> None:
        ti = TrustInput(
            candidate_claims=[CandidateClaim(
                statement="CTR increased 18%",
                proposed_type=ClaimType.FACT,
                proposed_confidence=88,
                is_metric_claim=True,
                evidence=[_ev("e1"), _ev("e2"), _ev("e3")],
            )],
            proposed_metrics=[ProposedMetric(
                name="ctr", inputs={"clicks": 18, "impressions": 100},
                source_tier=SourceTier.VERIFIED_PROVIDER,
            )],
        )
        out = validate_trust(ti)
        claim = out.claims[0]
        assert claim.claim_type is ClaimType.FACT
        assert claim.confidence == 95
        assert out.verdict is TrustVerdict.ACCEPT
        assert out.evidence_status is EvidenceStatus.OK
        assert out.invariant_violations == []


class TestTypeDemotion:
    def test_prose_fact_on_real_data_demotes_to_observation(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="The video is clearly our best performer",
            proposed_type=ClaimType.FACT,  # overclaimed
            is_metric_claim=False,
            evidence=[_ev("e1")],
        )])
        out = validate_trust(ti)
        assert out.claims[0].claim_type is ClaimType.OBSERVATION
        assert out.verdict is TrustVerdict.DOWNGRADE
        assert out.downgrades and out.downgrades[0].from_level == "fact"

    def test_no_grounding_source_demotes_to_hypothesis_and_insufficient(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="Reels probably beat static posts",
            proposed_type=ClaimType.OBSERVATION,
            evidence=[_ev("e1", tier=SourceTier.MODEL_INFERENCE)],
        )])
        out = validate_trust(ti)
        # model-inference only => insufficient band => no confidence.
        assert out.claims[0].status is ClaimStatus.INSUFFICIENT
        assert out.evidence_status is EvidenceStatus.INSUFFICIENT_EVIDENCE


class TestContradictionsSurfaced:
    def test_mixed_when_contradictions_present(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="Facebook outperforms Instagram for us",
            proposed_type=ClaimType.OBSERVATION,
            evidence=[_ev("s1"), _ev("s2"), _ev("c1", supports=False)],
        )])
        out = validate_trust(ti)
        assert out.claims[0].status is ClaimStatus.MIXED
        assert "c1" in out.claims[0].contradictions
        assert out.verdict is TrustVerdict.MIXED
        assert out.evidence_status is EvidenceStatus.MIXED_EVIDENCE


class TestCausalDowngradeInPipeline:
    def test_observational_causal_claim_downgraded(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="The new video caused the signup spike",
            proposed_type=ClaimType.OBSERVATION,
            is_causal_claim=True,
            causal_level=CausalLevel.OBSERVATIONAL,
            evidence=[_ev("e1")],
        )])
        out = validate_trust(ti)
        assert out.verdict is TrustVerdict.DOWNGRADE
        assert any(ca.downgraded for ca in out.causal_assessments)
        assert out.claims[0].limitations  # disclosure attached


class TestMetricClaimGating:
    def test_uncomputable_metric_claim_is_insufficient_and_rejected(self) -> None:
        ti = TrustInput(
            candidate_claims=[CandidateClaim(
                statement="ROAS was 5x",
                proposed_type=ClaimType.FACT,
                is_metric_claim=True,
                evidence=[_ev("e1")],
            )],
            proposed_metrics=[ProposedMetric(
                name="roas", inputs={"revenue": 100, "spend": 0},  # zero denom
                source_tier=SourceTier.VERIFIED_PROVIDER,
            )],
        )
        out = validate_trust(ti)
        assert out.claims[0].status is ClaimStatus.INSUFFICIENT
        assert out.claims[0].confidence == 0
        assert any(r.target == "roas" for r in out.rejections)


class TestEmptyAndRecommendations:
    def test_no_claims_is_insufficient(self) -> None:
        out = validate_trust(TrustInput(candidate_answer="hi"))
        assert out.evidence_status is EvidenceStatus.INSUFFICIENT_EVIDENCE
        assert out.verdict is TrustVerdict.INSUFFICIENT_EVIDENCE

    def test_recommendation_is_validated_in_pipeline(self) -> None:
        ti = TrustInput(candidate_recommendations=[CandidateRecommendation(
            statement="Increase ad spend substantially",
            consequence_level=ConsequenceLevel.HIGH,
            band=EvidenceBand.MODERATE,
            supporting_confidence=60,
            has_supporting_evidence=True,
            bears_on_action=True,
            source_tiers=[SourceTier.VERIFIED_PROVIDER],
        )])
        out = validate_trust(ti)
        rec = out.recommendations[0]
        assert rec.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW
        assert rec.requires_approval is True
