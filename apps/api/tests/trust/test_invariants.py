"""The 15 trust invariants (C14): adversarial inputs + a non-vacuous checker.

Two kinds of test here:
  * *behavioural* — feed the Trust Layer adversarial input and assert the
    produced output upholds the invariant (and ``invariant_violations`` is
    empty, i.e. the layer corrected rather than violated);
  * *checker* — hand a deliberately fabricated output to ``check_invariants``
    and assert it is detected, proving the checker is not vacuous.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aicmo.modules.trust.contracts import (
    CandidateClaim,
    CandidateRecommendation,
    CausalAssessment,
    Claim,
    ConfidenceFactors,
    EvidenceRef,
    MetricResult,
    ModelProvenance,
    ProposedMetric,
    Recommendation,
    TrustInput,
    TrustOutput,
)
from aicmo.modules.trust.enums import (
    CausalLevel,
    ClaimStatus,
    ClaimType,
    ConsequenceLevel,
    EvidenceBand,
    EvidenceStatus,
    ReasonCode,
    RecommendationStatus,
    SourceTier,
    TrustVerdict,
)
from aicmo.modules.trust.validation import check_invariants, validate_trust


def _ev(eid: str, *, supports: bool = True, tier: SourceTier = SourceTier.FIRST_PARTY_DATA) -> EvidenceRef:
    return EvidenceRef(evidence_id=eid, source_tier=tier, supports=supports)


# --- behavioural -------------------------------------------------------------

class TestBehavioural:
    def test_i1_layer_never_raises_confidence_above_ceiling(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="x", proposed_type=ClaimType.OBSERVATION,
            proposed_confidence=100, evidence=[_ev("e1")],
        )])
        out = validate_trust(ti)
        f = out.claims[0].confidence_factors
        assert f is not None
        assert out.claims[0].confidence <= f.derived <= max(f.applied_ceiling, 0)
        assert out.invariant_violations == []

    def test_i2_output_only_references_input_evidence(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="x", evidence=[_ev("e1"), _ev("e2")],
        )])
        out = validate_trust(ti)
        assert set(out.claims[0].evidence_ids) <= {"e1", "e2"}

    def test_i3_uncomputable_metric_never_gets_a_value(self) -> None:
        ti = TrustInput(proposed_metrics=[ProposedMetric(
            name="ctr", inputs={"clicks": 1, "impressions": 0},
            source_tier=SourceTier.FIRST_PARTY_DATA,
        )])
        out = validate_trust(ti)
        m = out.metric_results[0]
        assert not m.computable and m.value is None

    def test_i4_observational_causal_never_permitted(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="The promo caused the spike", is_causal_claim=True,
            causal_level=CausalLevel.OBSERVATIONAL, evidence=[_ev("e1")],
        )])
        out = validate_trust(ti)
        assert all(
            (not ca.permitted) for ca in out.causal_assessments if ca.is_causal_candidate
        )

    def test_i11_missing_evidence_yields_zero_confidence(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="unbacked claim", proposed_type=ClaimType.FACT, evidence=[],
        )])
        out = validate_trust(ti)
        assert out.claims[0].confidence == 0
        assert out.claims[0].status is ClaimStatus.INSUFFICIENT

    def test_i12_true_claim_does_not_auto_justify_action(self) -> None:
        # Strong evidence exists, but it does not bear on THIS action.
        ti = TrustInput(candidate_recommendations=[CandidateRecommendation(
            statement="Triple the budget",
            consequence_level=ConsequenceLevel.MEDIUM,
            band=EvidenceBand.STRONG, supporting_confidence=90,
            has_supporting_evidence=True, bears_on_action=False,
            source_tiers=[SourceTier.VERIFIED_PROVIDER],
        )])
        out = validate_trust(ti)
        assert out.recommendations[0].status is RecommendationStatus.INSUFFICIENT_EVIDENCE

    def test_i13_high_consequence_unsupported_requires_review(self) -> None:
        ti = TrustInput(candidate_recommendations=[CandidateRecommendation(
            statement="Launch the campaign",
            consequence_level=ConsequenceLevel.HIGH,
            band=EvidenceBand.WEAK, supporting_confidence=30,
            has_supporting_evidence=True, bears_on_action=True,
            source_tiers=[SourceTier.USER_PROVIDED],
        )])
        out = validate_trust(ti)
        rec = out.recommendations[0]
        assert rec.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW
        assert rec.requires_approval is True

    def test_i14_provider_identity_never_changes_the_decision(self) -> None:
        def build(provenance: ModelProvenance | None) -> TrustInput:
            return TrustInput(
                candidate_claims=[CandidateClaim(
                    statement="CTR increased 18%", proposed_type=ClaimType.FACT,
                    proposed_confidence=88, is_metric_claim=True,
                    evidence=[_ev("e1"), _ev("e2")],
                )],
                proposed_metrics=[ProposedMetric(
                    name="ctr", inputs={"clicks": 18, "impressions": 100},
                    source_tier=SourceTier.VERIFIED_PROVIDER,
                )],
                candidate_recommendations=[CandidateRecommendation(
                    statement="Shift budget to the winning creative",
                    consequence_level=ConsequenceLevel.MEDIUM,
                    band=EvidenceBand.MODERATE, supporting_confidence=65,
                    has_supporting_evidence=True, bears_on_action=True,
                    source_tiers=[SourceTier.FIRST_PARTY_DATA],
                )],
                model_provenance=provenance,
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )

        a = validate_trust(build(ModelProvenance(provider="anthropic", model="opus")))
        b = validate_trust(build(ModelProvenance(provider="openai", model="gpt")))
        c = validate_trust(build(None))
        assert a.model_dump() == b.model_dump() == c.model_dump()

    def test_adversarial_overclaim_is_contained(self) -> None:
        # Everything cranked: FACT, causal, LLM 100, but only weak hearsay.
        ti = TrustInput(candidate_claims=[CandidateClaim(
            statement="The rebrand definitely caused a 300% revenue jump",
            proposed_type=ClaimType.FACT, proposed_confidence=100,
            is_metric_claim=True, is_causal_claim=True,
            causal_level=CausalLevel.OBSERVATIONAL,
            evidence=[_ev("e1", tier=SourceTier.MODEL_INFERENCE)],
        )])
        out = validate_trust(ti)
        claim = out.claims[0]
        assert claim.claim_type is not ClaimType.FACT
        assert claim.confidence == 0
        assert out.evidence_status is EvidenceStatus.INSUFFICIENT_EVIDENCE
        assert out.invariant_violations == []


# --- checker is not vacuous --------------------------------------------------

def _factors(derived: int = 50, ceiling: int = 75) -> ConfidenceFactors:
    return ConfidenceFactors(
        band=EvidenceBand.MODERATE, claim_type=ClaimType.OBSERVATION, base=40,
        support_contribution=15, consistency_contribution=0,
        experimental_contribution=0, contradiction_penalty=0, raw=55,
        evidence_ceiling=ceiling, claim_ceiling=85, applied_ceiling=ceiling,
        floor=10, derived=derived, freshness_from=derived, final=derived,
    )


class TestCheckerDetectsFabrication:
    def test_detects_invented_evidence(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            claims=[Claim(statement="x", claim_type=ClaimType.OBSERVATION,
                          evidence_ids=["ghost"], confidence=10,
                          confidence_factors=_factors())],
        )
        assert ReasonCode.UNRESOLVABLE_EVIDENCE in check_invariants(TrustInput(), out)

    def test_detects_confidence_over_ceiling(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            claims=[Claim(statement="x", claim_type=ClaimType.OBSERVATION,
                          evidence_ids=[], confidence=99,
                          confidence_factors=_factors(derived=50, ceiling=75))],
        )
        assert ReasonCode.CONFIDENCE_OVER_CEILING in check_invariants(TrustInput(), out)

    def test_detects_fabricated_value_without_evidence(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            claims=[Claim(statement="x", claim_type=ClaimType.OBSERVATION,
                          evidence_ids=[], confidence=50, confidence_factors=None)],
        )
        assert ReasonCode.FABRICATED_METRIC in check_invariants(TrustInput(), out)

    def test_detects_hidden_contradiction(self) -> None:
        ti = TrustInput(candidate_claims=[CandidateClaim(statement="x", evidence=[_ev("c1", supports=False)])])
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            claims=[Claim(statement="x", claim_type=ClaimType.OBSERVATION,
                          evidence_ids=["c1"], contradictions=["c1"],
                          status=ClaimStatus.ACTIVE, confidence=40,
                          confidence_factors=_factors())],
        )
        assert ReasonCode.CONFLICTING_EVIDENCE in check_invariants(ti, out)

    def test_detects_metric_invention(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            metric_results=[MetricResult(name="ctr", value=None, computable=True)],
        )
        assert ReasonCode.FABRICATED_METRIC in check_invariants(TrustInput(), out)

    def test_detects_observational_causal_permitted(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            causal_assessments=[CausalAssessment(
                statement="x caused y", is_causal_candidate=True,
                evidence_level=CausalLevel.OBSERVATIONAL, permitted=True,
                downgraded=False)],
        )
        assert ReasonCode.UNSUPPORTED_CAUSAL_CLAIM in check_invariants(TrustInput(), out)

    def test_detects_high_risk_without_approval(self) -> None:
        out = TrustOutput(
            verdict=TrustVerdict.ACCEPT, evidence_status=EvidenceStatus.OK,
            recommendations=[Recommendation(
                statement="launch", consequence_level=ConsequenceLevel.HIGH,
                status=RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW,
                requires_approval=False)],
        )
        assert ReasonCode.HIGH_CONSEQUENCE_UNDER_EVIDENCED in check_invariants(TrustInput(), out)

    def test_clean_output_has_no_violations(self) -> None:
        out = validate_trust(TrustInput(candidate_claims=[CandidateClaim(
            statement="x", proposed_type=ClaimType.OBSERVATION, evidence=[_ev("e1")],
        )]))
        assert out.invariant_violations == []
