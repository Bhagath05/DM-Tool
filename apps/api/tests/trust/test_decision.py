"""T5 decision-quality — adversarial tests. The server decides decision quality
deterministically; the model cannot inflate it, hide counter-evidence, turn
correlation into causation, or let a repeated assertion become new evidence."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.trust.contracts import (
    CandidateClaim,
    CandidateRecommendation,
    EvidenceRef,
)
from aicmo.modules.trust.decision import evaluate_decision
from aicmo.modules.trust.enforcement import enforce
from aicmo.modules.trust.enums import (
    CausalLevel,
    ClaimType,
    ConsequenceLevel,
    EvidenceBand,
    RecommendationStatus,
    SourceTier,
)
from aicmo.modules.trust.recommendations import validate_recommendation
from aicmo.modules.trust.shadow import ShadowInput, validate_turn_shadow
from aicmo.tenancy.context import TenantContext

_ORG, _BRAND = uuid.uuid4(), uuid.uuid4()


def _tenant() -> TenantContext:
    return TenantContext(user_id="u", user_uuid=uuid.uuid4(), organization_id=_ORG,
                         brand_id=_BRAND, member_id=uuid.uuid4())


class _NoDB:
    async def execute(self, *a, **k):  # pragma: no cover
        raise AssertionError("no DB expected")


def _rec(**kw: object) -> CandidateRecommendation:
    base = CandidateRecommendation(
        statement="Increase budget 40%",
        consequence_level=ConsequenceLevel.HIGH,
        band=EvidenceBand.WEAK,
        supporting_confidence=35,
        has_supporting_evidence=True,
        bears_on_action=True,
    )
    return base.model_copy(update=kw) if kw else base


def _decide(rec: CandidateRecommendation):
    return evaluate_decision(rec, validate_recommendation(rec))


# --- decision-quality model (pure) ------------------------------------------


class TestDecisionQuality:
    def test_1_2_confidence_is_server_not_llm(self) -> None:
        # The decision confidence mirrors the server-validated value, whatever
        # the model proposed (the model's number isn't even an input here).
        d = _decide(_rec(supporting_confidence=40))
        assert d.confidence == 40

    def test_6_stale_evidence_flags_freshness_and_change(self) -> None:
        d = _decide(_rec(fresh=False))
        fresh = {f.name: f.assessment for f in d.factors}
        assert fresh["freshness"] == "weak"
        assert any("fresher data" in c.lower() for c in d.what_would_change)

    def test_7_contradiction_is_contradicted_and_preserved(self) -> None:
        d = _decide(_rec(contradicted=True, band=EvidenceBand.STRONG, supporting_confidence=90))
        assert d.status is RecommendationStatus.CONTRADICTED
        assert d.counter_evidence.contradicting >= 1

    def test_8_incomparable_cohorts_flagged(self) -> None:
        d = _decide(_rec(scope_match=False, band=EvidenceBand.MODERATE, supporting_confidence=65,
                         consequence_level=ConsequenceLevel.MEDIUM))
        comp = {f.name: f.assessment for f in d.factors}["comparability"]
        assert comp == "weak"
        assert any("same audience" in c.lower() for c in d.what_would_change)

    def test_9_observational_causal_names_controlled_experiment(self) -> None:
        d = _decide(_rec(causal_level=CausalLevel.OBSERVATIONAL))
        assert any("controlled experiment" in c.lower() for c in d.what_would_change)
        assert {f.name: f.assessment for f in d.factors}["causal_strength"] == "weak"

    def test_10_19_unsupported_action_is_insufficient(self) -> None:
        d = _decide(_rec(has_supporting_evidence=False, consequence_level=ConsequenceLevel.LOW))
        assert d.status is RecommendationStatus.INSUFFICIENT_EVIDENCE

    def test_12_20_high_consequence_weak_requires_review_and_suggests_test(self) -> None:
        d = _decide(_rec(consequence_level=ConsequenceLevel.HIGH, band=EvidenceBand.WEAK,
                         supporting_confidence=30, reversible=False))
        assert d.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW
        assert d.requires_approval is True
        assert d.suggested_experiment is not None
        assert d.suggested_experiment.approval_required is True

    def test_17_insufficient_does_not_become_confident(self) -> None:
        d = _decide(_rec(consequence_level=ConsequenceLevel.LOW, band=EvidenceBand.INSUFFICIENT,
                         supporting_confidence=20, has_supporting_evidence=False))
        assert d.status is RecommendationStatus.INSUFFICIENT_EVIDENCE
        assert d.suggested_experiment is not None  # propose a test instead of certainty

    def test_supported_still_names_what_would_change(self) -> None:
        # Genuine intelligence: even a supported low-risk rec names its disproof.
        d = _decide(_rec(consequence_level=ConsequenceLevel.LOW, band=EvidenceBand.STRONG,
                         supporting_confidence=80, supporting_count=3, scope_match=True,
                         expected_effect="+10%", testable=True, reversible=True))
        assert d.status is RecommendationStatus.SUPPORTED
        assert len(d.what_would_change) >= 1

    def test_evaluate_does_not_change_server_status(self) -> None:
        rec = _rec(consequence_level=ConsequenceLevel.HIGH, band=EvidenceBand.WEAK, supporting_confidence=30)
        validated = validate_recommendation(rec)
        d = evaluate_decision(rec, validated)
        assert d.status is validated.status
        assert d.confidence == validated.confidence
        assert d.requires_approval == validated.requires_approval


# --- through the enforcement envelope ---------------------------------------


async def _enforce_si(si: ShadowInput):
    shadow = await validate_turn_shadow(cast(AsyncSession, _NoDB()), tenant=_tenant(), shadow_input=si)
    return enforce(shadow)


@pytest.mark.asyncio
class TestDecisionInEnvelope:
    async def test_envelope_recommendation_carries_decision_quality(self) -> None:
        enf = await _enforce_si(ShadowInput(
            candidate_claims=[CandidateClaim(statement="x", proposed_type=ClaimType.OBSERVATION,
                                             evidence=[EvidenceRef(evidence_id="a", kind="belief")])],
            candidate_recommendations=[_rec(consequence_level=ConsequenceLevel.HIGH,
                                            band=EvidenceBand.WEAK, supporting_confidence=30,
                                            causal_level=CausalLevel.OBSERVATIONAL)],
        ))
        r = enf.envelope.recommendations[0]
        assert r.what_would_change
        assert r.suggested_experiment is not None
        assert r.counter_evidence is not None
        assert r.factors

    async def test_15_repeated_identical_claim_is_not_new_evidence(self) -> None:
        # The same claim proposed twice does not raise the server confidence —
        # confidence is derived from the retrieved evidence, not from repetition.
        ev = [EvidenceRef(evidence_id="b1", kind="belief", source_tier=SourceTier.FIRST_PARTY_DATA)]
        one = await _enforce_si(ShadowInput(candidate_claims=[
            CandidateClaim(statement="Reels win", proposed_type=ClaimType.OBSERVATION, evidence=list(ev)),
        ]))
        twice = await _enforce_si(ShadowInput(candidate_claims=[
            CandidateClaim(statement="Reels win", proposed_type=ClaimType.OBSERVATION, evidence=list(ev)),
            CandidateClaim(statement="Reels win", proposed_type=ClaimType.OBSERVATION, evidence=list(ev)),
        ]))
        # Overall (weakest-link) confidence is not inflated by the repetition.
        assert twice.confidence == one.confidence
        assert all(c.confidence == one.envelope.claims[0].confidence for c in twice.envelope.claims)

    async def test_18_mixed_evidence_keeps_both_sides(self) -> None:
        enf = await _enforce_si(ShadowInput(candidate_claims=[
            CandidateClaim(statement="Campaign worked", proposed_type=ClaimType.OBSERVATION,
                           evidence=[
                               EvidenceRef(evidence_id="up", kind="belief", source_tier=SourceTier.FIRST_PARTY_DATA),
                               EvidenceRef(evidence_id="down", kind="belief", source_tier=SourceTier.FIRST_PARTY_DATA, supports=False),
                           ]),
        ]))
        claim = enf.envelope.claims[0]
        assert claim.trust_status.value == "mixed_evidence"
        # the contradicting side is preserved, not dropped
        assert "down" in claim.limitations or claim.evidence_labels
