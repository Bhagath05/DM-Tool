"""Shadow Trust validation for the agent turn (T2).

Observes the structured candidate an agent turn produced, validates it with the
T0 deterministic core and T1 read-only provenance resolver, and returns a
**shadow result** plus a safe structured audit payload. It is *observation only*:

* It never changes the candidate, blocks it, executes a tool, approves an
  action, or enforces a Trust decision.
* The LLM's confidence is diagnostic only; authoritative confidence is derived
  by T0, independent of the model.
* Evidence references are resolved through T1 and, crucially, any reference that
  fails to resolve (unknown / cross-tenant / malformed) is **stripped** before
  T0 sees it — an invalid reference can never become valid evidence.

This module is agent-agnostic: it takes T0/T1 contracts, not agent objects, so
the runtime wiring stays a thin adapter and this logic is fully unit-testable.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.trust.contracts import (
    CandidateClaim,
    CandidateRecommendation,
    EvidenceRef,
    ModelProvenance,
    ProposedMetric,
    Recommendation,
    TrustInput,
    TrustOutput,
)
from aicmo.modules.trust.enums import (
    ClaimStatus,
    ConsequenceLevel,
    EvidenceBand,
    RecommendationStatus,
    SourceTier,
)
from aicmo.modules.trust.provenance import (
    EvidenceReference,
    ProvenanceResolution,
    ResolutionStatus,
    resolve_references,
)
from aicmo.modules.trust.recommendations import validate_recommendation
from aicmo.modules.trust.validation import validate_trust
from aicmo.tenancy.context import TenantContext

VALIDATOR_VERSION = "t2.v1"

_BAND_RANK: dict[EvidenceBand, int] = {
    EvidenceBand.INSUFFICIENT: 0,
    EvidenceBand.WEAK: 1,
    EvidenceBand.MODERATE: 2,
    EvidenceBand.STRONG: 3,
}


class ShadowInput(BaseModel):
    """The structured candidate to validate in shadow. Built by the runtime from
    fields the agent turn already produces — never reconstructed chain-of-thought,
    never prose parsed into imaginary claims."""

    model_config = ConfigDict(extra="forbid")

    candidate_claims: list[CandidateClaim] = Field(default_factory=list)
    candidate_recommendations: list[CandidateRecommendation] = Field(default_factory=list)
    proposed_metrics: list[ProposedMetric] = Field(default_factory=list)
    proposed_causal_statements: list[str] = Field(default_factory=list)
    # T1 references to resolve (tenant-scoped, read-only). Any that back a claim
    # but fail to resolve are stripped from that claim's evidence.
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    # Diagnostic only — recorded, never an input to server-derived confidence.
    llm_confidence: int | None = None
    llm_evidence_status: str | None = None
    model_provenance: ModelProvenance | None = None


class ShadowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust: TrustOutput
    provenance: ProvenanceResolution
    llm_confidence: int | None = None
    llm_evidence_status: str | None = None
    server_confidence: int = 0
    confidence_delta: int | None = None  # server - llm (negative => llm over-claimed)
    confidence_inflated: bool = False  # llm claimed more than the evidence supports
    audit: dict = Field(default_factory=dict)
    error: str | None = None


def _aggregate(trust: TrustOutput) -> tuple[EvidenceBand, int, bool, list[SourceTier]]:
    """Weakest-link aggregate over the turn's graded claims — used to validate a
    recommendation against the evidence that actually stands this turn."""
    graded = [c for c in trust.claims if c.status in (ClaimStatus.ACTIVE, ClaimStatus.MIXED)]
    if not graded:
        return EvidenceBand.INSUFFICIENT, 0, False, []
    band = min(
        (c.confidence_factors.band for c in graded if c.confidence_factors is not None),
        key=lambda b: _BAND_RANK[b],
        default=EvidenceBand.WEAK,
    )
    tiers: list[SourceTier] = []
    for c in graded:
        tiers.extend(c.source_tiers)
    return band, trust.overall_confidence, True, tiers


def _is_default_rec(rec: CandidateRecommendation) -> bool:
    """True when the caller left the evidence fields unspecified (the runtime
    path), so they should be filled from the turn's claims."""
    return (
        rec.supporting_confidence == 0
        and rec.band is EvidenceBand.INSUFFICIENT
        and not rec.has_supporting_evidence
    )


def _enriched_rec(rec: CandidateRecommendation, agg: tuple) -> CandidateRecommendation:
    band, conf, has_support, tiers = agg
    return rec.model_copy(
        update={
            "band": band,
            "supporting_confidence": conf,
            "has_supporting_evidence": has_support,
            # Same-turn heuristic: the turn's evidence plausibly bears on the
            # turn's proposed action. Conservative — no evidence => no bearing.
            "bears_on_action": has_support,
            "source_tiers": tiers,
        }
    )


def _bridge_claims(
    claims: list[CandidateClaim], provenance: ProvenanceResolution
) -> tuple[list[CandidateClaim], int]:
    """Strip/annotate each claim's evidence against T1: a submitted reference that
    did not resolve (unknown / cross-tenant / malformed) is removed so it can
    never count as valid evidence. Returns (bridged claims, stripped count)."""
    resolved = {r.evidence_id: r for r in provenance.resolved if r.status is ResolutionStatus.RESOLVED}
    submitted = {r.evidence_id for r in provenance.resolved}
    stripped = 0
    out: list[CandidateClaim] = []
    for claim in claims:
        kept: list[EvidenceRef] = []
        for ev in claim.evidence:
            if ev.evidence_id in submitted and ev.evidence_id not in resolved:
                stripped += 1  # failed T1 resolution → not valid evidence
                continue
            r = resolved.get(ev.evidence_id)
            if r is not None:
                kept.append(ev.model_copy(update={
                    "source_tier": r.source_tier or ev.source_tier,
                    "observed_at": r.observed_at or ev.observed_at,
                }))
            else:
                kept.append(ev)  # not submitted for resolution → caller's assertion
        out.append(claim.model_copy(update={"evidence": kept}))
    return out, stripped


def _audit(
    trust: TrustOutput,
    provenance: ProvenanceResolution,
    *,
    llm_confidence: int | None,
    server_confidence: int,
    stripped_refs: int,
    causal_candidates: int,
) -> dict:
    claim_status = {s: 0 for s in ("active", "mixed", "contradicted", "insufficient", "superseded")}
    for c in trust.claims:
        claim_status[c.status.value] = claim_status.get(c.status.value, 0) + 1
    rec_status = {s.value: 0 for s in RecommendationStatus}
    consequence = {c.value: 0 for c in ConsequenceLevel}
    for r in trust.recommendations:
        rec_status[r.status.value] += 1
        consequence[r.consequence_level.value] += 1
    unresolved = sum(1 for r in provenance.resolved if r.status is not ResolutionStatus.RESOLVED)
    cross_tenant = sum(1 for r in provenance.resolved if r.status is ResolutionStatus.TENANT_MISMATCH)
    unknown = sum(1 for r in provenance.resolved if r.status is ResolutionStatus.UNKNOWN_EVIDENCE)
    stale = sum(
        1 for r in provenance.resolved
        if r.freshness is not None and r.freshness.is_expired
    )
    not_computable = sum(1 for m in trust.metric_results if not m.computable)
    causal_downgraded = sum(1 for a in trust.causal_assessments if a.downgraded)
    delta = (server_confidence - llm_confidence) if llm_confidence is not None else None
    return {
        "validator_version": VALIDATOR_VERSION,
        "trust_verdict": trust.verdict.value,
        "evidence_status": trust.evidence_status.value,
        "claim_count": len(trust.claims),
        "claim_supported": claim_status["active"],
        "claim_mixed": claim_status["mixed"],
        "claim_contradicted": claim_status["contradicted"],
        "claim_insufficient": claim_status["insufficient"],
        "recommendation_count": len(trust.recommendations),
        "recommendation_status": rec_status,
        "recommendation_consequence": consequence,
        "high_risk_recommendations": rec_status[RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW.value],
        "evidence_refs": len(provenance.resolved),
        "evidence_resolved": len(provenance.resolved) - unresolved,
        "evidence_unresolved": unresolved,
        "evidence_cross_tenant": cross_tenant,
        "evidence_unknown": unknown,
        "evidence_stripped_from_claims": stripped_refs,
        "stale_evidence": stale,
        "metric_count": len(trust.metric_results),
        "metric_not_computable": not_computable,
        "causal_candidates": causal_candidates,
        "causal_overclaims_downgraded": causal_downgraded,
        "llm_confidence": llm_confidence,
        "server_confidence": server_confidence,
        "confidence_delta": delta,
        "confidence_inflated": bool(llm_confidence is not None and llm_confidence > server_confidence),
        "invariant_violations": [v.value for v in trust.invariant_violations],
    }


async def validate_turn_shadow(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    shadow_input: ShadowInput,
    now: datetime | None = None,
) -> ShadowResult:
    """Run one shadow validation pass over a turn's structured candidate.

    Deterministic results (including ``INSUFFICIENT_EVIDENCE``) are returned, not
    swallowed. This function performs read-only DB access only (T1), computes
    nothing the user sees, and never executes or approves anything.
    """
    # 1. T1: resolve referenced evidence (bounded, tenant-scoped, read-only).
    provenance = (
        await resolve_references(session, tenant=tenant, references=shadow_input.evidence_refs, now=now)
        if shadow_input.evidence_refs
        else ProvenanceResolution()
    )

    # 2. Bridge: invalid references must not become valid evidence.
    bridged_claims, stripped = _bridge_claims(shadow_input.candidate_claims, provenance)

    # 3. T0: validate claims + metrics + causality (deterministic, model-independent).
    trust = validate_trust(
        TrustInput(
            candidate_claims=bridged_claims,
            proposed_metrics=shadow_input.proposed_metrics,
            proposed_causal_statements=shadow_input.proposed_causal_statements,
            model_provenance=shadow_input.model_provenance,
            now=now,
        )
    )

    # 4. Recommendations: evidence for a claim is not evidence for an action.
    #    Validate each independently; fill unspecified evidence fields from the
    #    turn's claim aggregate (weakest link).
    agg = _aggregate(trust)
    recs: list[Recommendation] = []
    for rec in shadow_input.candidate_recommendations:
        candidate = _enriched_rec(rec, agg) if _is_default_rec(rec) else rec
        recs.append(validate_recommendation(candidate))
    trust.recommendations = recs

    server_confidence = trust.overall_confidence
    audit = _audit(
        trust, provenance,
        llm_confidence=shadow_input.llm_confidence,
        server_confidence=server_confidence,
        stripped_refs=stripped,
        causal_candidates=sum(1 for a in trust.causal_assessments if a.is_causal_candidate),
    )
    delta = (
        server_confidence - shadow_input.llm_confidence
        if shadow_input.llm_confidence is not None
        else None
    )
    return ShadowResult(
        trust=trust,
        provenance=provenance,
        llm_confidence=shadow_input.llm_confidence,
        llm_evidence_status=shadow_input.llm_evidence_status,
        server_confidence=server_confidence,
        confidence_delta=delta,
        confidence_inflated=bool(
            shadow_input.llm_confidence is not None
            and shadow_input.llm_confidence > server_confidence
        ),
        audit=audit,
    )
