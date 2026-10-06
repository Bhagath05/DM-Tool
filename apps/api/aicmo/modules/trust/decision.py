"""Deterministic decision-quality model (Trust Layer T5).

A claim being true does not make an action wise. T0's
:func:`aicmo.modules.trust.recommendations.validate_recommendation` already
decides a recommendation's trust *status*; T5 adds, deterministically and
server-side, the **decision quality** around it:

* a structured breakdown of the decision factors (evidence quality, quantity,
  freshness, consistency, comparability, causal strength, consequence,
  contradictions, reversibility, testability),
* the **counter-evidence** (supporting vs contradicting vs missing),
* **"what would change this conclusion"** — the evidence that would overturn or
  strengthen it (genuine intelligence names its own failure conditions), and
* a **safe experiment suggestion** when the evidence is too thin for a strong
  recommendation (recommendation only — never executed here).

This module computes nothing from prose and invents no numbers: it reads the
already-validated, server-derived facts. The LLM proposes; the server decides.
It reuses T0 contracts/enums and never duplicates the status logic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.trust.contracts import CandidateRecommendation, Recommendation
from aicmo.modules.trust.enums import (
    CausalLevel,
    ConsequenceLevel,
    EvidenceBand,
    RecommendationStatus,
)

# Causal levels strong enough to permit genuine causal action-justification.
_STRONG_CAUSAL = frozenset({CausalLevel.CONTROLLED_EXPERIMENT, CausalLevel.RANDOMIZED})
_WEAK_CAUSAL = frozenset({CausalLevel.OBSERVATIONAL, CausalLevel.ASSOCIATIONAL})


class DecisionFactor(BaseModel):
    """One deterministic input to the decision, with a plain assessment label."""

    model_config = ConfigDict(extra="forbid")

    name: str
    assessment: str  # strong | adequate | weak | absent | n/a
    detail: str


class CounterEvidence(BaseModel):
    """What supports the action, what works against it, and what is missing.
    Contradictions and gaps are preserved, never silently dropped."""

    model_config = ConfigDict(extra="forbid")

    supporting: int = 0
    contradicting: int = 0
    missing: list[str] = Field(default_factory=list)


class SuggestedExperiment(BaseModel):
    """A safe test to run when evidence is too thin to recommend confidently.
    Recommendation only — it always requires human approval and is never
    executed by the Trust Layer."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: str
    variants: list[str] = Field(default_factory=list)
    hold_constant: list[str] = Field(default_factory=list)
    success_metric: str
    approval_required: bool = True


class DecisionQuality(BaseModel):
    """The server-derived decision-quality assessment for one recommendation."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    status: RecommendationStatus
    consequence: ConsequenceLevel
    confidence: int
    requires_approval: bool
    factors: list[DecisionFactor] = Field(default_factory=list)
    counter_evidence: CounterEvidence
    what_would_change: list[str] = Field(default_factory=list)
    suggested_experiment: SuggestedExperiment | None = None
    limitations: list[str] = Field(default_factory=list)


def _band_assessment(band: EvidenceBand) -> str:
    return {
        EvidenceBand.STRONG: "strong",
        EvidenceBand.MODERATE: "adequate",
        EvidenceBand.WEAK: "weak",
        EvidenceBand.INSUFFICIENT: "absent",
    }[band]


def _count_assessment(n: int) -> str:
    if n <= 0:
        return "absent"
    if n == 1:
        return "weak"
    if n == 2:
        return "adequate"
    return "strong"


def _causal_assessment(level: CausalLevel | None) -> str:
    if level is None:
        return "n/a"
    if level in _STRONG_CAUSAL:
        return "strong"
    if level is CausalLevel.QUASI_EXPERIMENTAL:
        return "adequate"
    return "weak"  # observational / associational


def _factors(rec: CandidateRecommendation) -> list[DecisionFactor]:
    supporting = rec.supporting_count or (1 if rec.has_supporting_evidence else 0)
    contradicting = rec.contradicting_count or (1 if rec.contradicted else 0)
    return [
        DecisionFactor(name="evidence_quality", assessment=_band_assessment(rec.band),
                       detail=f"Evidence band is {rec.band.value}."),
        DecisionFactor(name="evidence_quantity", assessment=_count_assessment(supporting),
                       detail=f"{supporting} supporting observation(s)."),
        DecisionFactor(name="freshness", assessment="adequate" if rec.fresh else "weak",
                       detail="Evidence is current." if rec.fresh else "Evidence may be stale."),
        DecisionFactor(name="consistency", assessment="adequate" if contradicting == 0 else "weak",
                       detail="No contradictions." if contradicting == 0 else f"{contradicting} contradicting signal(s)."),
        DecisionFactor(name="comparability", assessment="adequate" if rec.scope_match else "weak",
                       detail="Same scope as the action." if rec.scope_match else "Evidence is from a different scope."),
        DecisionFactor(name="causal_strength", assessment=_causal_assessment(rec.causal_level),
                       detail=(f"Causal basis: {rec.causal_level.value}." if rec.causal_level else "No causal claim.")),
        DecisionFactor(name="sample_size", assessment="adequate" if rec.sample_adequate else "weak",
                       detail="Sample is adequate." if rec.sample_adequate else "Sample is small."),
        DecisionFactor(name="consequence", assessment=rec.consequence_level.value,
                       detail=f"Action consequence is {rec.consequence_level.value}."),
        DecisionFactor(name="reversibility",
                       assessment="adequate" if rec.reversible else "weak" if rec.reversible is False else "n/a",
                       detail="Reversible." if rec.reversible else "Not easily reversible." if rec.reversible is False else "Reversibility unknown."),
        DecisionFactor(name="testability", assessment="adequate" if rec.testable else "weak",
                       detail="Can be tested." if rec.testable else "No stated way to test the outcome."),
    ]


def _what_would_change(rec: CandidateRecommendation, status: RecommendationStatus) -> list[str]:
    """Deterministic 'evidence that would change this conclusion'. Even a
    SUPPORTED conclusion names what would overturn it."""
    changes: list[str] = []
    if rec.band in (EvidenceBand.WEAK, EvidenceBand.INSUFFICIENT) or not rec.sample_adequate:
        changes.append("A larger, more consistent set of comparable observations.")
    if rec.causal_level is not None and rec.causal_level in _WEAK_CAUSAL:
        changes.append(
            f"A controlled experiment — current evidence is only {rec.causal_level.value} "
            "and cannot establish causation."
        )
    if not rec.fresh:
        changes.append("Fresher data from the current period.")
    if rec.contradicted or rec.contradicting_count > 0:
        changes.append("Resolving the conflicting signals with a clean, comparable test.")
    if not rec.scope_match:
        changes.append("Evidence from the same audience, objective, and creative format.")
    if not rec.has_supporting_evidence:
        changes.append("Any verified supporting data for this specific action.")
    if rec.consequence_level is ConsequenceLevel.HIGH and status is not RecommendationStatus.SUPPORTED:
        changes.append("Verified first-party evidence before acting at this consequence level.")
    # Genuine intelligence: a supported conclusion still names its own disproof.
    if not changes:
        changes.append("Contradictory results from a new comparable experiment would overturn this.")
    # Dedup, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for c in changes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _suggested_experiment(
    rec: CandidateRecommendation, status: RecommendationStatus
) -> SuggestedExperiment | None:
    """When evidence is too thin for a strong recommendation, propose a safe test
    instead of pretending certainty. Recommendation only; approval required."""
    if status not in (
        RecommendationStatus.INSUFFICIENT_EVIDENCE,
        RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW,
        RecommendationStatus.QUALIFIED,
    ):
        return None
    return SuggestedExperiment(
        hypothesis=f"Whether \"{rec.statement}\" holds up under a controlled comparison.",
        variants=["the proposed change", "the current baseline"],
        hold_constant=["audience", "objective", "creative format", "budget", "time window"],
        success_metric=rec.expected_effect or "a primary metric agreed before the test starts",
        approval_required=True,
    )


def evaluate_decision(
    rec: CandidateRecommendation, validated: Recommendation
) -> DecisionQuality:
    """Assemble the deterministic decision-quality view for one recommendation.
    ``validated`` is the authoritative status/confidence from T0's
    :func:`validate_recommendation`; this never changes it, only explains it and
    names what would change it."""
    supporting = rec.supporting_count or (1 if rec.has_supporting_evidence else 0)
    contradicting = rec.contradicting_count or (1 if rec.contradicted else 0)
    missing = _what_would_change(rec, validated.status)
    return DecisionQuality(
        statement=validated.statement,
        status=validated.status,
        consequence=validated.consequence_level,
        confidence=validated.confidence,
        requires_approval=validated.requires_approval,
        factors=_factors(rec),
        counter_evidence=CounterEvidence(
            supporting=supporting, contradicting=contradicting, missing=missing,
        ),
        what_would_change=missing,
        suggested_experiment=_suggested_experiment(rec, validated.status),
        limitations=list(validated.limitations),
    )
