"""Typed, pure DTOs for the Trust Layer (T0).

Every model is ``extra="forbid"`` so authority/ORM/secret fields cannot be
smuggled in. Nothing here is an ORM object, a session, a callable, or a secret;
tenant context, if present, is carried only as opaque string identity/scope
metadata (never authority). None of these are persisted.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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

# Distinguishing scope dimensions — two claims are only "about the same slice"
# when they agree on every shared one. Mirrors the belief reconcile semantics but
# is kept here so the Trust module stays pure (no ORM-coupled import).
_DISTINGUISHING_KEYS: frozenset[str] = frozenset(
    {
        "channel", "platform", "audience", "segment", "icp", "metric", "window",
        "measurement_window", "action_kind", "record_type", "market", "campaign",
        "content_type", "creative_format", "offer",
    }
)


def scopes_comparable(a: dict, b: dict) -> bool:
    """True only when two scopes describe the same slice: at least one shared
    distinguishing dimension and agreement on every shared distinguishing
    dimension. Different scopes are never comparable (so they never contradict)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    shared = [k for k in _DISTINGUISHING_KEYS if k in a and k in b]
    if not shared:
        return False
    return all(str(a[k]).strip().lower() == str(b[k]).strip().lower() for k in shared)


class TenantRef(BaseModel):
    """Opaque tenant identity for provenance/correlation ONLY — never authority.
    T0 never reads a tenant, enforces nothing from it, and makes no decision with
    it; it exists only so a recorded trust result can be correlated later."""

    model_config = ConfigDict(extra="forbid")

    organization_id: str
    brand_id: str | None = None


class ModelProvenance(BaseModel):
    """Provider/model identity — provenance ONLY. Never affects any Trust Layer
    decision, ceiling, band, or value (model-independence invariant)."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model: str | None = None


class EvidenceRef(BaseModel):
    """A reference to a real, already-stored evidence row (by id). T0 does not
    resolve it (that is T1); it carries the id, kind, source tier, and the
    relation to the claim so pure validation can reason about it."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: str = "unknown"  # e.g. belief / brain_evidence / advisor_outcome
    source_tier: SourceTier = SourceTier.UNKNOWN
    supports: bool = True  # False = contradicting evidence
    observed_at: datetime | None = None


class ProposedMetric(BaseModel):
    """A metric the candidate answer wants to state, with its raw inputs. The
    Trust Layer computes it deterministically (never trusts an LLM value)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    inputs: dict[str, float | int | None] = Field(default_factory=dict)
    source_tier: SourceTier = SourceTier.UNKNOWN


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float | None = None
    unit: str = ""
    computable: bool = False
    reason_code: ReasonCode | None = None
    source_tier: SourceTier = SourceTier.UNKNOWN


class ConfidenceFactors(BaseModel):
    """Structured, explainable breakdown of the derived confidence. This is NOT
    chain-of-thought — it is the arithmetic of a deterministic formula."""

    model_config = ConfigDict(extra="forbid")

    band: EvidenceBand
    claim_type: ClaimType
    base: int
    support_contribution: int
    consistency_contribution: int
    experimental_contribution: int
    contradiction_penalty: int
    raw: int
    evidence_ceiling: int
    claim_ceiling: int
    applied_ceiling: int
    floor: int
    derived: int
    freshness_from: int
    final: int
    llm_proposed_diagnostic: int | None = None  # recorded; NEVER an input
    reasons: list[str] = Field(default_factory=list)


class CandidateClaim(BaseModel):
    """What the LLM proposes. ``proposed_type`` / ``proposed_confidence`` are
    diagnostic only; the Trust Layer assigns the authoritative type + confidence.
    Supporting/contradicting counts and consistency come from structured
    evidence, not prose."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    proposed_type: ClaimType | None = None
    proposed_confidence: int | None = None  # diagnostic only
    evidence: list[EvidenceRef] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    observed_at: datetime | None = None
    is_metric_claim: bool = False
    is_causal_claim: bool = False
    causal_level: CausalLevel | None = None
    consistent: bool = True  # all supporting evidence points the same direction
    experimental: bool = False  # backed by a measured outcome/experiment


class Claim(BaseModel):
    """The validated, typed claim the Trust Layer emits. Not persisted."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    claim_type: ClaimType
    evidence_ids: list[str] = Field(default_factory=list)
    source_tiers: list[SourceTier] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    observed_at: datetime | None = None
    causal_level: CausalLevel | None = None
    confidence: int = 0
    confidence_factors: ConfidenceFactors | None = None
    limitations: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.ACTIVE


class CausalAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    is_causal_candidate: bool
    evidence_level: CausalLevel
    permitted: bool
    downgraded: bool
    suggested_statement: str | None = None
    disclosure: str | None = None
    reason_code: ReasonCode | None = None


class CandidateRecommendation(BaseModel):
    """A recommended action proposed by the candidate, with the structured facts
    the Trust Layer needs to validate it independently of the prose."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    consequence_level: ConsequenceLevel = ConsequenceLevel.LOW
    supporting_confidence: int = 0  # effective confidence of the weakest supporting claim
    band: EvidenceBand = EvidenceBand.INSUFFICIENT
    has_supporting_evidence: bool = False
    bears_on_action: bool = True  # does the evidence bear on THIS action, not just a related claim
    scope_match: bool = True
    contradicted: bool = False
    expected_effect: str | None = None
    downside: str | None = None
    reversible: bool | None = None
    testable: bool = False
    source_tiers: list[SourceTier] = Field(default_factory=list)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    consequence_level: ConsequenceLevel
    status: RecommendationStatus
    confidence: int = 0
    requires_approval: bool = False
    limitations: list[str] = Field(default_factory=list)
    reasons: list[ReasonCode] = Field(default_factory=list)


class Downgrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    from_level: str
    to_level: str
    reason_code: ReasonCode


class Rejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    reason_code: ReasonCode


class TrustInput(BaseModel):
    """Everything the Trust Layer needs — and nothing it must not have. No ORM
    objects, sessions, callables, secrets, or model-supplied authority."""

    model_config = ConfigDict(extra="forbid")

    candidate_answer: str = ""
    candidate_claims: list[CandidateClaim] = Field(default_factory=list)
    proposed_metrics: list[ProposedMetric] = Field(default_factory=list)
    proposed_causal_statements: list[str] = Field(default_factory=list)
    candidate_recommendations: list[CandidateRecommendation] = Field(default_factory=list)
    model_provenance: ModelProvenance | None = None  # provenance only
    tenant_ref: TenantRef | None = None  # identity only; never authority
    now: datetime | None = None


class TrustOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: TrustVerdict
    evidence_status: EvidenceStatus
    overall_confidence: int = 0
    claims: list[Claim] = Field(default_factory=list)
    metric_results: list[MetricResult] = Field(default_factory=list)
    causal_assessments: list[CausalAssessment] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    downgrades: list[Downgrade] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    invariant_violations: list[ReasonCode] = Field(default_factory=list)
