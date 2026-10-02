"""Trust Layer orchestration + machine-testable invariants (T0).

``validate_trust`` is the pure entry point: it takes a :class:`TrustInput`
(structured, already-fetched signals — no DB, no network, no LLM) and returns a
:class:`TrustOutput` with typed claims, deterministically computed metrics,
causal assessments, validated recommendations, and an overall verdict.

It composes the other pure modules:
  * :mod:`confidence`      — server-derived confidence (independent of any LLM),
  * :mod:`metrics`         — the deterministic metric registry,
  * :mod:`causality`       — the correlation→causation gate,
  * :mod:`recommendations` — the decision-intelligence recommendation gate,
  * :mod:`sources`         — provenance grounding predicates.

``check_invariants`` asserts the 15 trust invariants (C14) over the produced
output; any violation forces a fail-closed ``REJECT``. The Trust Layer only ever
**demotes / qualifies / rejects** — it never raises confidence, promotes a claim
type, invents evidence, or lowers an approval requirement.
"""

from __future__ import annotations

from datetime import datetime

from aicmo.modules.trust.causality import assess_causality
from aicmo.modules.trust.confidence import derive_confidence
from aicmo.modules.trust.contracts import (
    CandidateClaim,
    Claim,
    Downgrade,
    MetricResult,
    Rejection,
    TrustInput,
    TrustOutput,
)
from aicmo.modules.trust.enums import (
    CausalLevel,
    ClaimStatus,
    ClaimType,
    EvidenceBand,
    EvidenceStatus,
    ReasonCode,
    RecommendationStatus,
    TrustVerdict,
)
from aicmo.modules.trust.metrics import compute_metric
from aicmo.modules.trust.recommendations import validate_recommendation
from aicmo.modules.trust.sources import is_grounding, is_monetary_grade

# Factual trust ladder (higher = more trust). RECOMMENDATION is off this ladder.
_TRUST_RANK: dict[ClaimType, int] = {
    ClaimType.FACT: 4,
    ClaimType.OBSERVATION: 3,
    ClaimType.INTERPRETATION: 2,
    ClaimType.HYPOTHESIS: 1,
    ClaimType.RECOMMENDATION: 0,
}
_RANK_TO_TYPE: dict[int, ClaimType] = {v: k for k, v in _TRUST_RANK.items()}


def assess_band(
    *,
    supporting_count: int,
    grounding_source_count: int,
    has_verified_source: bool,
    contradiction_count: int,
    consistent: bool,
) -> EvidenceBand:
    """Deterministic evidence-quality band (§6). Freshness is applied later as a
    multiplier, not here, so the band reflects source quality + quantity +
    consistency + contradictions only."""
    if supporting_count <= 0 or grounding_source_count <= 0:
        return EvidenceBand.INSUFFICIENT
    if contradiction_count >= 2:
        return EvidenceBand.WEAK
    if has_verified_source and supporting_count >= 2 and contradiction_count == 0 and consistent:
        return EvidenceBand.STRONG
    if (has_verified_source or supporting_count >= 2) and contradiction_count == 0:
        return EvidenceBand.MODERATE
    return EvidenceBand.WEAK


def _max_allowed_type(
    *, has_grounding: bool, fact_eligible: bool, causal_blocked: bool
) -> ClaimType:
    # FACT is reserved for a verified, deterministically computed metric; a plain
    # prose claim on real data is at most an OBSERVATION.
    if fact_eligible:
        cap = ClaimType.FACT
    elif has_grounding:
        cap = ClaimType.OBSERVATION
    else:
        cap = ClaimType.HYPOTHESIS
    if causal_blocked and _TRUST_RANK[cap] > _TRUST_RANK[ClaimType.OBSERVATION]:
        cap = ClaimType.OBSERVATION
    return cap


def _authoritative_type(proposed: ClaimType | None, cap: ClaimType, *, has_grounding: bool) -> ClaimType:
    """Trust Layer only ever *demotes*: authoritative = the lower-trust of the
    proposed type and the evidence-allowed cap."""
    if proposed is None:
        proposed = ClaimType.OBSERVATION if has_grounding else ClaimType.HYPOTHESIS
    # A recommendation stated as a claim is treated as an interpretation here;
    # action trust is validated separately (recommendations.py).
    if proposed is ClaimType.RECOMMENDATION:
        proposed = ClaimType.INTERPRETATION
    rank = min(_TRUST_RANK[proposed], _TRUST_RANK[cap])
    return _RANK_TO_TYPE[rank]


def _reference_time(claim: CandidateClaim) -> datetime | None:
    if claim.observed_at is not None:
        return claim.observed_at
    stamps = [e.observed_at for e in claim.evidence if e.observed_at is not None]
    return max(stamps) if stamps else None


def _validate_claim(
    claim: CandidateClaim, *, metric_results: list[MetricResult], now: datetime | None
) -> Claim:
    supporting = [e for e in claim.evidence if e.supports]
    contradicting = [e for e in claim.evidence if not e.supports]
    source_tiers = [e.source_tier for e in claim.evidence]
    grounding = [t for t in source_tiers if is_grounding(t)]
    has_grounding = bool(grounding)
    has_verified = any(is_monetary_grade(t) for t in source_tiers)

    # A metric claim must be backed by a computable metric; FACT additionally
    # requires that computed metric to come from a verified source.
    metric_backed = any(m.computable for m in metric_results)
    metric_ok = (not claim.is_metric_claim) or metric_backed
    fact_eligible = claim.is_metric_claim and metric_backed and has_verified

    # Causal gate feeds both the type cap and the claim's disclosures.
    causal_assessment = None
    causal_blocked = False
    if claim.is_causal_claim or claim.causal_level is not None:
        causal_assessment = assess_causality(
            statement=claim.statement,
            evidence_level=claim.causal_level or CausalLevel.OBSERVATIONAL,
            is_causal_candidate=claim.is_causal_claim or None,
            source_tiers=source_tiers,
        )
        causal_blocked = causal_assessment.is_causal_candidate and not causal_assessment.permitted

    cap = _max_allowed_type(
        has_grounding=has_grounding, fact_eligible=fact_eligible,
        causal_blocked=causal_blocked,
    )
    claim_type = _authoritative_type(claim.proposed_type, cap, has_grounding=has_grounding)

    band = assess_band(
        supporting_count=len(supporting),
        grounding_source_count=len(grounding),
        has_verified_source=has_verified,
        contradiction_count=len(contradicting),
        consistent=claim.consistent,
    )

    limitations: list[str] = []
    contradictions: list[str] = []
    if claim.is_metric_claim and not metric_ok:
        limitations.append("Metric could not be computed from real data; not shown as fact.")
        band = EvidenceBand.INSUFFICIENT
    if causal_assessment is not None and causal_assessment.downgraded:
        if causal_assessment.disclosure:
            limitations.append(causal_assessment.disclosure)
    if contradicting:
        contradictions = [e.evidence_id for e in contradicting]

    factors = derive_confidence(
        band=band,
        claim_type=claim_type,
        supporting_count=len(supporting),
        contradiction_count=len(contradicting),
        consistent=claim.consistent,
        experimental=claim.experimental,
        reference_time=_reference_time(claim),
        now=now,
        recommendation_support_confidence=None,
        llm_proposed=claim.proposed_confidence,
    )

    # Status: contradictions are surfaced, never hidden.
    if band is EvidenceBand.INSUFFICIENT or factors.final <= 0 or not supporting:
        status = ClaimStatus.INSUFFICIENT
    elif contradicting and not supporting:
        status = ClaimStatus.CONTRADICTED
    elif contradicting:
        status = ClaimStatus.MIXED
    else:
        status = ClaimStatus.ACTIVE

    return Claim(
        statement=claim.statement,
        claim_type=claim_type,
        evidence_ids=[e.evidence_id for e in claim.evidence],
        source_tiers=source_tiers,
        scope=claim.scope,
        observed_at=claim.observed_at,
        causal_level=claim.causal_level,
        confidence=factors.final,
        confidence_factors=factors,
        limitations=limitations,
        contradictions=contradictions,
        status=status,
    )


def _evidence_status(claims: list[Claim]) -> EvidenceStatus:
    if not claims:
        return EvidenceStatus.INSUFFICIENT_EVIDENCE
    if any(c.status in (ClaimStatus.MIXED, ClaimStatus.CONTRADICTED) for c in claims):
        return EvidenceStatus.MIXED_EVIDENCE
    if all(c.status is ClaimStatus.INSUFFICIENT for c in claims):
        return EvidenceStatus.INSUFFICIENT_EVIDENCE
    return EvidenceStatus.OK


def check_invariants(trust_input: TrustInput, output: TrustOutput) -> list[ReasonCode]:
    """Assert the 15 trust invariants (C14) over the produced output. Returns the
    list of violated reason codes — it should always be empty; a non-empty list
    means the layer must fail closed (REJECT)."""
    violations: list[ReasonCode] = []
    known_ids = {e.evidence_id for c in trust_input.candidate_claims for e in c.evidence}

    for claim in output.claims:
        f = claim.confidence_factors
        # I1: never raise above the derived value or the applied ceiling.
        if f is not None and (claim.confidence > f.derived or claim.confidence > max(f.applied_ceiling, 0)):
            violations.append(ReasonCode.CONFIDENCE_OVER_CEILING)
        # I2: never invent evidence.
        if any(eid not in known_ids for eid in claim.evidence_ids):
            violations.append(ReasonCode.UNRESOLVABLE_EVIDENCE)
        # I11: missing evidence can never become a fabricated value.
        if not claim.evidence_ids and claim.confidence > 0:
            violations.append(ReasonCode.FABRICATED_METRIC)
        # I5: contradictions are never hidden.
        if claim.contradictions and claim.status is ClaimStatus.ACTIVE:
            violations.append(ReasonCode.CONFLICTING_EVIDENCE)

    # I3: never invent a metric.
    for m in output.metric_results:
        if m.computable and m.value is None:
            violations.append(ReasonCode.FABRICATED_METRIC)
        if not m.computable and m.value is not None:
            violations.append(ReasonCode.NOT_COMPUTABLE)

    # I4: never turn weak evidence into a permitted causal claim.
    permitted_causal = {CausalLevel.CONTROLLED_EXPERIMENT, CausalLevel.RANDOMIZED}
    for ca in output.causal_assessments:
        if ca.is_causal_candidate and ca.permitted and ca.evidence_level not in permitted_causal:
            violations.append(ReasonCode.UNSUPPORTED_CAUSAL_CLAIM)

    candidates = {r.statement: r for r in trust_input.candidate_recommendations}
    for rec in output.recommendations:
        src = candidates.get(rec.statement)
        # I12 / I15: a SUPPORTED/QUALIFIED recommendation must have its own
        # resolvable supporting evidence that bears on the action — a true claim
        # never auto-justifies it.
        if rec.status in (RecommendationStatus.SUPPORTED, RecommendationStatus.QUALIFIED):
            if src is None or not src.has_supporting_evidence or not src.bears_on_action:
                violations.append(ReasonCode.RECOMMENDATION_EXCEEDS_EVIDENCE)
        # I13: a HIGH-consequence under-evidenced rec is never SUPPORTED and
        # always keeps its approval requirement.
        if rec.status is RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW and not rec.requires_approval:
            violations.append(ReasonCode.HIGH_CONSEQUENCE_UNDER_EVIDENCED)

    return violations


def _overall_verdict(
    output: TrustOutput, *, demoted: bool, qualified: bool
) -> TrustVerdict:
    if output.invariant_violations:
        return TrustVerdict.REJECT
    if output.evidence_status is EvidenceStatus.INSUFFICIENT_EVIDENCE:
        return TrustVerdict.INSUFFICIENT_EVIDENCE
    if output.evidence_status is EvidenceStatus.MIXED_EVIDENCE:
        return TrustVerdict.MIXED
    if demoted:
        return TrustVerdict.DOWNGRADE
    if qualified:
        return TrustVerdict.QUALIFY
    return TrustVerdict.ACCEPT


def validate_trust(trust_input: TrustInput) -> TrustOutput:
    """Pure Trust Layer entry point. Deterministic in its inputs; the result is
    identical regardless of ``model_provenance`` (model-independence, I14)."""
    now = trust_input.now

    metric_results = [compute_metric(m) for m in trust_input.proposed_metrics]
    claims = [
        _validate_claim(c, metric_results=metric_results, now=now)
        for c in trust_input.candidate_claims
    ]

    # Standalone causal statements, then the causal assessments produced while
    # typing claims (so a causal claim's downgrade is visible in the output).
    causal_assessments = [
        assess_causality(statement=s, evidence_level=CausalLevel.OBSERVATIONAL)
        for s in trust_input.proposed_causal_statements
    ]
    for c in trust_input.candidate_claims:
        if c.is_causal_claim or c.causal_level is not None:
            causal_assessments.append(
                assess_causality(
                    statement=c.statement,
                    evidence_level=c.causal_level or CausalLevel.OBSERVATIONAL,
                    is_causal_candidate=c.is_causal_claim or None,
                    source_tiers=[e.source_tier for e in c.evidence],
                )
            )

    recommendations = [validate_recommendation(r) for r in trust_input.candidate_recommendations]

    # Record downgrades (never silently drop evidence — C13).
    downgrades: list[Downgrade] = []
    for src, out in zip(trust_input.candidate_claims, claims, strict=False):
        if src.proposed_type is not None:
            proposed = (
                ClaimType.INTERPRETATION
                if src.proposed_type is ClaimType.RECOMMENDATION
                else src.proposed_type
            )
            if _TRUST_RANK[out.claim_type] < _TRUST_RANK[proposed]:
                downgrades.append(
                    Downgrade(
                        target=out.statement, from_level=proposed.value,
                        to_level=out.claim_type.value,
                        reason_code=ReasonCode.UNVERIFIED_SOURCE,
                    )
                )
    for ca in causal_assessments:
        if ca.downgraded:
            downgrades.append(
                Downgrade(
                    target=ca.statement, from_level=ca.evidence_level.value,
                    to_level="association",
                    reason_code=ca.reason_code or ReasonCode.UNSUPPORTED_CAUSAL_CLAIM,
                )
            )

    rejections = [
        Rejection(target=m.name, reason_code=m.reason_code or ReasonCode.NOT_COMPUTABLE)
        for m in metric_results
        if not m.computable
    ]

    demoted = bool(downgrades)
    qualified = any(c.limitations for c in claims) or any(
        r.status is RecommendationStatus.QUALIFIED for r in recommendations
    )

    limitations: list[str] = []
    for c in claims:
        limitations.extend(c.limitations)

    graded = [c.confidence for c in claims if c.status in (ClaimStatus.ACTIVE, ClaimStatus.MIXED)]
    output = TrustOutput(
        verdict=TrustVerdict.ACCEPT,  # replaced below once invariants are known
        evidence_status=_evidence_status(claims),
        overall_confidence=min(graded) if graded else 0,
        claims=claims,
        metric_results=metric_results,
        causal_assessments=causal_assessments,
        recommendations=recommendations,
        downgrades=downgrades,
        rejections=rejections,
        limitations=sorted(set(limitations)),
    )
    output.invariant_violations = check_invariants(trust_input, output)
    output.verdict = _overall_verdict(output, demoted=demoted, qualified=qualified)
    return output
