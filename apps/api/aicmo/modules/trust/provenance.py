"""Read-only evidence provenance resolver (Trust Layer T1).

Answers "why did DM Tool say this?" over **existing durable evidence**, without
ever writing, executing, retrieving new external data, crossing tenants, or
touching the agent/approvals. It takes safe evidence references plus a trusted
server ``TenantContext`` and returns structured provenance — allowlisted fields
only, never raw rows, secrets, sessions, or chain-of-thought.

Guarantees (pinned by tests):

* **Read-only.** Only ``SELECT`` statements are issued — no INSERT/UPDATE/DELETE,
  no flush/commit, no external/provider/agent calls.
* **Tenant isolation, fail closed.** Every query is scoped by the server
  context's ``brand_id`` (the same guard belief evidence already uses). A
  reference to another tenant's row resolves as ``UNKNOWN_EVIDENCE`` —
  indistinguishable from nonexistent, so existence never leaks. Tenant authority
  is NEVER taken from the reference: a reference that *claims* a different
  tenant than the server context is rejected ``TENANT_MISMATCH`` before any read.
* **No fabrication.** Missing/invalid references stay failures; incomplete
  provenance is represented as incomplete, never filled by assumption.
* **Reuse, don't duplicate.** Source tiers come from T0 (:mod:`trust.enums`),
  derived-metric provenance from T0's registry (:mod:`trust.metrics`), and
  freshness from the audited belief resolver (:mod:`belief.freshness`).

T1 is the read-only foundation only. It is NOT wired into ``run_turn`` and does
NOT alter any user-visible response (that is T2).
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
from aicmo.modules.belief.freshness import effective_confidence, is_expired
from aicmo.modules.belief.models import Belief, BeliefEvidence
from aicmo.modules.business_brain.models import BrainEvidence, BrainResearchJob
from aicmo.modules.learning.models import LearningInsight
from aicmo.modules.trust.contracts import ProposedMetric
from aicmo.modules.trust.enums import ReasonCode, SourceTier
from aicmo.modules.trust.metrics import compute_metric
from aicmo.tenancy.context import TenantContext

# Hard ceiling on references resolved per request — bounds DB reads, prevents an
# unbounded evidence-fan-out from a crafted candidate answer.
MAX_REFERENCES = 50


class EvidenceKind(enum.StrEnum):
    """The durable evidence kinds T1 can resolve. Mirrors the belief evidence
    vocabulary (plus ``belief`` itself for claim→evidence tracing)."""

    BRAIN_EVIDENCE = "brain_evidence"
    ADVISOR_RECOMMENDATION = "advisor_recommendation"
    ADVISOR_OUTCOME = "advisor_outcome"
    LEARNING_INSIGHT = "learning_insight"
    BELIEF = "belief"


class ResolutionStatus(enum.StrEnum):
    """Whether a reference resolved, and if not, why (fail-closed reasons)."""

    RESOLVED = "resolved"
    UNKNOWN_EVIDENCE = "unknown_evidence"  # nonexistent OR another tenant's (no leak)
    TENANT_MISMATCH = "tenant_mismatch"  # reference claimed a tenant != server context
    INVALID_REFERENCE = "invalid_reference"  # malformed id / unknown kind


class ProvenanceFlag(enum.StrEnum):
    """Soft annotations on a resolved row — it resolved, but carries a caveat."""

    MISSING_PROVENANCE = "missing_provenance"
    STALE_EVIDENCE = "stale_evidence"
    UNVERIFIED_SOURCE = "unverified_source"
    SMALL_SAMPLE = "small_sample"


class ObservedOrDerived(enum.StrEnum):
    OBSERVED = "observed"  # recorded/measured from a source
    DERIVED = "derived"  # computed/synthesised internally
    UNKNOWN = "unknown"


class ProvenanceCompleteness(enum.StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INCOMPLETE = "incomplete"


# ---------------------------------------------------------------------------
# DTOs (extra="forbid" — no ORM objects, sessions, secrets, or authority)
# ---------------------------------------------------------------------------


class EvidenceReference(BaseModel):
    """A safe reference to resolve. ``kind`` + ``evidence_id`` identify the row;
    the optional ``claimed_*`` fields are diagnostic only and, if present, must
    match the server context (else ``TENANT_MISMATCH``) — they never grant
    authority."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: str
    claimed_organization_id: str | None = None
    claimed_brand_id: str | None = None


class ResearchProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_job_id: str
    provider: str | None = None
    status: str | None = None
    verified_provider: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FreshnessInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_time: datetime | None = None
    expires_at: datetime | None = None
    is_expired: bool = False
    stored_confidence: int | None = None
    effective_confidence: int | None = None
    decay_reason: str | None = None


class ScopeInfo(BaseModel):
    """Bounded comparison scope for comparability analysis in T0/T2. Only
    populated with dimensions actually present on the evidence — never guessed."""

    model_config = ConfigDict(extra="forbid")

    dimensions: dict[str, str] = Field(default_factory=dict)


class MetricProvenance(BaseModel):
    """Observed raw inputs vs the deterministically derived value (T0 registry).
    The LLM is never the calculation authority."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    calculator_id: str  # the registry metric the value was computed by
    raw_inputs: dict[str, float | int | None] = Field(default_factory=dict)
    computable: bool = False
    value: float | None = None
    unit: str = ""
    reason_code: ReasonCode | None = None
    source_tier: SourceTier = SourceTier.UNKNOWN


class ResolvedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: str
    status: ResolutionStatus
    # populated only when status == RESOLVED
    source: str | None = None  # e.g. source_url / source_surface
    source_tier: SourceTier | None = None
    claim_type: str | None = None  # brain_evidence kind (fact/observation/...)
    observed_or_derived: ObservedOrDerived = ObservedOrDerived.UNKNOWN
    discovered_at: datetime | None = None
    observed_at: datetime | None = None
    freshness: FreshnessInfo | None = None
    scope: ScopeInfo | None = None
    research: ResearchProvenance | None = None
    metric_provenance: MetricProvenance | None = None
    stored_confidence: int | None = None
    completeness: ProvenanceCompleteness = ProvenanceCompleteness.INCOMPLETE
    flags: list[ProvenanceFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ProvenanceResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved: list[ResolvedEvidence] = Field(default_factory=list)
    requested: int = 0
    truncated: bool = False


class BeliefProvenanceChain(BaseModel):
    """CLAIM → EVIDENCE for recommendation/belief traceability. The belief is the
    claim; ``supporting``/``contradicting`` are its resolved evidence rows."""

    model_config = ConfigDict(extra="forbid")

    belief: ResolvedEvidence
    supporting: list[ResolvedEvidence] = Field(default_factory=list)
    contradicting: list[ResolvedEvidence] = Field(default_factory=list)
    incomplete_refs: int = 0


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def resolve_metric_provenance(proposed: ProposedMetric) -> MetricProvenance:
    """Observed-vs-derived for a metric: the raw inputs are the OBSERVED facts;
    the value is DERIVED deterministically by T0's registry. Pure (no DB)."""
    result = compute_metric(proposed)
    return MetricProvenance(
        metric_name=result.name,
        calculator_id=f"trust.metrics:{proposed.name.strip().lower()}",
        raw_inputs=dict(proposed.inputs),
        computable=result.computable,
        value=result.value,
        unit=result.unit,
        reason_code=result.reason_code,
        source_tier=proposed.source_tier,
    )


def _bounded_dimensions(raw: dict) -> dict[str, str]:
    """Allowlisted, stringified, length-bounded comparison dimensions."""
    allowed = (
        "platform", "format", "content_format", "audience", "audience_segment",
        "segment", "time_window", "window", "campaign", "campaign_type", "channel",
        "metric", "spend", "offer", "market",
    )
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for key in allowed:
        if key in raw and raw[key] is not None:
            out[key] = str(raw[key])[:120]
    return out


def _freshness(
    *, stored_confidence: int | None, reference_time: datetime | None,
    expires_at: datetime | None, now: datetime | None,
) -> FreshnessInfo:
    expired = is_expired(expires_at, now=now)
    eff: int | None = None
    reason: str | None = None
    if stored_confidence is not None:
        eff, reason = effective_confidence(
            original_confidence=stored_confidence, reference_time=reference_time, now=now
        )
    return FreshnessInfo(
        reference_time=reference_time,
        expires_at=expires_at,
        is_expired=expired,
        stored_confidence=stored_confidence,
        effective_confidence=eff,
        decay_reason=reason,
    )


# ---------------------------------------------------------------------------
# Per-kind row → ResolvedEvidence mappers (pure; operate on allowlisted columns)
# ---------------------------------------------------------------------------


def _map_brain_evidence(row, *, now: datetime | None) -> ResolvedEvidence:
    (eid, kind, category, confidence, status, source_url,
     source_type, discovered_at, research_job_id) = row
    flags: list[ProvenanceFlag] = []
    limitations: list[str] = []
    tier = SourceTier.USER_PROVIDED if source_type == "user" else SourceTier.RESEARCH
    if not source_url:
        flags.append(ProvenanceFlag.MISSING_PROVENANCE)
        limitations.append("No source URL recorded for this claim.")
    if status != "active":
        limitations.append(f"Claim status is '{status}' (not active).")
    complete = (
        ProvenanceCompleteness.COMPLETE
        if source_url and research_job_id
        else ProvenanceCompleteness.PARTIAL if source_url
        else ProvenanceCompleteness.INCOMPLETE
    )
    fresh = _freshness(
        stored_confidence=confidence, reference_time=discovered_at, expires_at=None, now=now
    )
    return ResolvedEvidence(
        evidence_id=str(eid), kind=EvidenceKind.BRAIN_EVIDENCE.value,
        status=ResolutionStatus.RESOLVED, source=source_url, source_tier=tier,
        claim_type=kind, observed_or_derived=ObservedOrDerived.OBSERVED,
        discovered_at=discovered_at, observed_at=discovered_at, freshness=fresh,
        scope=ScopeInfo(dimensions=_bounded_dimensions({"metric": category})),
        stored_confidence=confidence, completeness=complete, flags=flags,
        limitations=limitations,
    )


def _map_advisor_recommendation(row, *, now: datetime | None) -> ResolvedEvidence:
    (eid, record_type, status, confidence, impact_category, created_at, completed_at) = row
    limitations = ["Advisory recommendation — never self-authorizing for execution."]
    if status != "completed":
        limitations.append(f"Recommendation status is '{status}'.")
    fresh = _freshness(
        stored_confidence=confidence, reference_time=completed_at or created_at,
        expires_at=None, now=now,
    )
    return ResolvedEvidence(
        evidence_id=str(eid), kind=EvidenceKind.ADVISOR_RECOMMENDATION.value,
        status=ResolutionStatus.RESOLVED, source="advisor", source_tier=SourceTier.DERIVED_INTERNAL,
        observed_or_derived=ObservedOrDerived.DERIVED, discovered_at=created_at,
        observed_at=completed_at, freshness=fresh,
        scope=ScopeInfo(dimensions=_bounded_dimensions(
            {"metric": impact_category, "campaign_type": record_type}
        )),
        stored_confidence=confidence, completeness=ProvenanceCompleteness.PARTIAL,
        limitations=limitations,
    )


def _map_advisor_outcome(row, *, now: datetime | None) -> ResolvedEvidence:
    (eid, evaluation_status, evaluate_after, evaluated_at) = row
    flags: list[ProvenanceFlag] = []
    limitations: list[str] = []
    if evaluation_status == "insufficient_data":
        flags.append(ProvenanceFlag.SMALL_SAMPLE)
        limitations.append("Outcome had insufficient data to evaluate.")
    if evaluation_status == "pending":
        limitations.append("Outcome not yet evaluated.")
    complete = (
        ProvenanceCompleteness.COMPLETE
        if evaluation_status == "evaluated" and evaluated_at
        else ProvenanceCompleteness.PARTIAL
    )
    # A measured effectiveness is OBSERVED (experimental); confidence is not stored
    # here, so freshness ages the observation timestamp without a stored value.
    fresh = _freshness(
        stored_confidence=None, reference_time=evaluated_at or evaluate_after,
        expires_at=None, now=now,
    )
    return ResolvedEvidence(
        evidence_id=str(eid), kind=EvidenceKind.ADVISOR_OUTCOME.value,
        status=ResolutionStatus.RESOLVED, source="advisor_outcome_evaluation",
        source_tier=SourceTier.DERIVED_INTERNAL, observed_or_derived=ObservedOrDerived.OBSERVED,
        discovered_at=evaluate_after, observed_at=evaluated_at, freshness=fresh,
        completeness=complete, flags=flags, limitations=limitations,
    )


def _map_learning_insight(row, *, now: datetime | None) -> ResolvedEvidence:
    (eid, category, confidence, learned_at, expires_at, source, status) = row
    flags: list[ProvenanceFlag] = []
    limitations: list[str] = []
    fresh = _freshness(
        stored_confidence=confidence, reference_time=learned_at, expires_at=expires_at, now=now
    )
    if fresh.is_expired:
        flags.append(ProvenanceFlag.STALE_EVIDENCE)
        limitations.append("Lesson has expired (past its validity window).")
    if source == "auto":
        limitations.append("Auto-synthesised lesson (not user-affirmed).")
    if status != "active":
        limitations.append(f"Insight status is '{status}'.")
    return ResolvedEvidence(
        evidence_id=str(eid), kind=EvidenceKind.LEARNING_INSIGHT.value,
        status=ResolutionStatus.RESOLVED, source="learning_engine",
        source_tier=SourceTier.DERIVED_INTERNAL, observed_or_derived=ObservedOrDerived.DERIVED,
        discovered_at=learned_at, observed_at=learned_at, freshness=fresh,
        scope=ScopeInfo(dimensions=_bounded_dimensions({"metric": category})),
        stored_confidence=confidence, completeness=ProvenanceCompleteness.PARTIAL,
        flags=flags, limitations=limitations,
    )


def _map_belief(row, *, now: datetime | None) -> ResolvedEvidence:
    (eid, category, scope, status, confidence, validated_at,
     valid_from, valid_until) = row
    flags: list[ProvenanceFlag] = []
    limitations: list[str] = []
    fresh = _freshness(
        stored_confidence=confidence, reference_time=validated_at or valid_from,
        expires_at=valid_until, now=now,
    )
    if fresh.is_expired:
        flags.append(ProvenanceFlag.STALE_EVIDENCE)
        limitations.append("Belief validity window has closed.")
    if status != "active":
        limitations.append(f"Belief status is '{status}'.")
    dims = _bounded_dimensions(scope if isinstance(scope, dict) else {})
    dims.setdefault("metric", str(category))
    return ResolvedEvidence(
        evidence_id=str(eid), kind=EvidenceKind.BELIEF.value,
        status=ResolutionStatus.RESOLVED, source="belief_memory",
        source_tier=SourceTier.DERIVED_INTERNAL, observed_or_derived=ObservedOrDerived.DERIVED,
        discovered_at=valid_from, observed_at=validated_at, freshness=fresh,
        scope=ScopeInfo(dimensions=dims), stored_confidence=confidence,
        completeness=ProvenanceCompleteness.PARTIAL, flags=flags, limitations=limitations,
    )


# kind → (allowlisted column select builder, mapper, research-job column index).
# Hardcoded — never built from caller input, so a malicious kind cannot select
# arbitrary fields.
_KIND_SELECTS = {
    EvidenceKind.BRAIN_EVIDENCE.value: (
        lambda ids, brand: select(
            BrainEvidence.id, BrainEvidence.kind, BrainEvidence.category,
            BrainEvidence.confidence, BrainEvidence.status,
            BrainEvidence.source_url, BrainEvidence.source_type,
            BrainEvidence.discovered_at, BrainEvidence.research_job_id,
        ).where(BrainEvidence.id.in_(ids), BrainEvidence.brand_id == brand),
        _map_brain_evidence,
        8,  # index of research_job_id in the row (for the research batch)
    ),
    EvidenceKind.ADVISOR_RECOMMENDATION.value: (
        lambda ids, brand: select(
            AdvisorRecommendation.id, AdvisorRecommendation.record_type,
            AdvisorRecommendation.status, AdvisorRecommendation.confidence,
            AdvisorRecommendation.impact_category, AdvisorRecommendation.created_at,
            AdvisorRecommendation.completed_at,
        ).where(AdvisorRecommendation.id.in_(ids), AdvisorRecommendation.brand_id == brand),
        _map_advisor_recommendation,
        None,
    ),
    EvidenceKind.ADVISOR_OUTCOME.value: (
        lambda ids, brand: select(
            AdvisorOutcome.id, AdvisorOutcome.evaluation_status,
            AdvisorOutcome.evaluate_after, AdvisorOutcome.evaluated_at,
        ).where(AdvisorOutcome.id.in_(ids), AdvisorOutcome.brand_id == brand),
        _map_advisor_outcome,
        None,
    ),
    EvidenceKind.LEARNING_INSIGHT.value: (
        lambda ids, brand: select(
            LearningInsight.id, LearningInsight.category, LearningInsight.confidence,
            LearningInsight.learned_at, LearningInsight.expires_at,
            LearningInsight.source, LearningInsight.status,
        ).where(LearningInsight.id.in_(ids), LearningInsight.brand_id == brand),
        _map_learning_insight,
        None,
    ),
    EvidenceKind.BELIEF.value: (
        lambda ids, brand: select(
            Belief.id, Belief.category, Belief.scope,
            Belief.status, Belief.confidence, Belief.validated_at,
            Belief.valid_from, Belief.valid_until,
        ).where(Belief.id.in_(ids), Belief.brand_id == brand),
        _map_belief,
        None,
    ),
}

# belief_evidence.ref_kind → resolvable EvidenceKind (DATA_SOURCE has no row).
_REFKIND_TO_EVIDENCE: dict[str, str] = {
    "brain_evidence": EvidenceKind.BRAIN_EVIDENCE.value,
    "advisor_recommendation": EvidenceKind.ADVISOR_RECOMMENDATION.value,
    "advisor_outcome": EvidenceKind.ADVISOR_OUTCOME.value,
    "learning_insight": EvidenceKind.LEARNING_INSIGHT.value,
}


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise ValueError("A brand must be selected to resolve provenance.")
    return tenant.brand_id


def _tenant_mismatch(ref: EvidenceReference, tenant: TenantContext, brand: uuid.UUID) -> bool:
    """True if the reference *claims* a tenant different from the server context.
    Authority always comes from ``tenant``; this only rejects a disagreeing claim
    (never a probe of another tenant — that path returns UNKNOWN_EVIDENCE)."""
    if ref.claimed_brand_id is not None and ref.claimed_brand_id != str(brand):
        return True
    if (
        ref.claimed_organization_id is not None
        and ref.claimed_organization_id != str(tenant.organization_id)
    ):
        return True
    return False


def _parse_id(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


async def resolve_references(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    references: Sequence[EvidenceReference],
    now: datetime | None = None,
) -> ProvenanceResolution:
    """Batch-resolve evidence references (read-only, tenant-scoped, bounded).

    Preserves input order in the output. Groups by kind so each kind is a single
    ``SELECT ... WHERE id = ANY(:ids) AND brand_id = :brand`` (no N+1). Unknown
    ids, cross-tenant ids, malformed ids, and disagreeing tenant claims all fail
    closed without leaking existence.
    """
    brand = _require_brand(tenant)
    requested = len(references)
    truncated = requested > MAX_REFERENCES
    refs = list(references[:MAX_REFERENCES])

    # Pre-validate; collect DB lookups per kind for the valid ones.
    results: dict[int, ResolvedEvidence] = {}
    by_kind: dict[str, dict[uuid.UUID, int]] = {}
    for idx, ref in enumerate(refs):
        if ref.kind not in _KIND_SELECTS:
            results[idx] = ResolvedEvidence(
                evidence_id=ref.evidence_id, kind=ref.kind,
                status=ResolutionStatus.INVALID_REFERENCE,
                limitations=[f"Unknown evidence kind '{ref.kind}'."],
            )
            continue
        if _tenant_mismatch(ref, tenant, brand):
            results[idx] = ResolvedEvidence(
                evidence_id=ref.evidence_id, kind=ref.kind,
                status=ResolutionStatus.TENANT_MISMATCH,
                limitations=["Reference claimed a tenant other than the active one."],
            )
            continue
        parsed = _parse_id(ref.evidence_id)
        if parsed is None:
            results[idx] = ResolvedEvidence(
                evidence_id=ref.evidence_id, kind=ref.kind,
                status=ResolutionStatus.INVALID_REFERENCE,
                limitations=["Malformed evidence id."],
            )
            continue
        by_kind.setdefault(ref.kind, {})[parsed] = idx

    research_job_ids: set[uuid.UUID] = set()
    research_targets: list[tuple[int, uuid.UUID]] = []  # (result idx, research_job_id)

    for kind, id_to_idx in by_kind.items():
        stmt_builder, mapper, research_col = _KIND_SELECTS[kind]
        stmt: Select = stmt_builder(list(id_to_idx.keys()), brand)
        rows = (await session.execute(stmt)).all()
        seen: set[uuid.UUID] = set()
        for row in rows:
            row_id = row[0]
            idx = id_to_idx.get(row_id)
            if idx is None:
                continue  # defensive: never map a row we didn't ask for
            seen.add(row_id)
            results[idx] = mapper(row, now=now)
            if research_col is not None and row[research_col] is not None:
                rj = row[research_col]
                research_job_ids.add(rj)
                research_targets.append((idx, rj))
        # ids we asked for but didn't get back → unknown (or cross-tenant).
        for missing_id, idx in id_to_idx.items():
            if missing_id not in seen:
                results[idx] = ResolvedEvidence(
                    evidence_id=str(missing_id), kind=kind,
                    status=ResolutionStatus.UNKNOWN_EVIDENCE,
                    limitations=["Evidence not found for the active tenant."],
                )

    # One bounded batch for referenced research jobs (brand-scoped) → provider.
    if research_job_ids:
        rj_rows = (
            await session.execute(
                select(
                    BrainResearchJob.id, BrainResearchJob.provider,
                    BrainResearchJob.status, BrainResearchJob.started_at,
                    BrainResearchJob.finished_at,
                ).where(
                    BrainResearchJob.id.in_(research_job_ids),
                    BrainResearchJob.brand_id == brand,
                )
            )
        ).all()
        jobs = {r[0]: r for r in rj_rows}
        for idx, rj in research_targets:
            job = jobs.get(rj)
            if job is None:
                continue
            _, provider, status, started_at, finished_at = job
            results[idx].research = ResearchProvenance(
                research_job_id=str(rj), provider=provider, status=status,
                verified_provider=False,  # research provider is NOT an ad-platform verified source
                started_at=started_at, finished_at=finished_at,
            )

    ordered = [results[i] for i in range(len(refs))]
    return ProvenanceResolution(resolved=ordered, requested=requested, truncated=truncated)


async def resolve_belief_chain(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    belief_id: str,
    now: datetime | None = None,
) -> BeliefProvenanceChain | None:
    """Resolve a belief (the CLAIM) and its supporting/contradicting EVIDENCE —
    the chain a recommendation is ultimately traceable through. Read-only and
    tenant-scoped; returns ``None`` if the belief is not available for the tenant."""
    brand = _require_brand(tenant)
    parsed = _parse_id(belief_id)
    if parsed is None:
        return None

    belief_res = await resolve_references(
        session, tenant=tenant,
        references=[EvidenceReference(evidence_id=str(parsed), kind=EvidenceKind.BELIEF.value)],
        now=now,
    )
    belief = belief_res.resolved[0]
    if belief.status is not ResolutionStatus.RESOLVED:
        return None

    ref_rows = (
        await session.execute(
            select(BeliefEvidence.ref_kind, BeliefEvidence.ref_id, BeliefEvidence.relation)
            .where(BeliefEvidence.belief_id == parsed, BeliefEvidence.brand_id == brand)
            .order_by(BeliefEvidence.created_at.asc(), BeliefEvidence.id.asc())
        )
    ).all()

    supporting_refs: list[EvidenceReference] = []
    contradicting_idx: list[bool] = []
    incomplete = 0
    for ref_kind, ref_id, relation in ref_rows:
        kind = _REFKIND_TO_EVIDENCE.get(ref_kind)
        if kind is None or ref_id is None:
            incomplete += 1  # DATA_SOURCE label or unmapped kind — no resolvable row
            continue
        supporting_refs.append(EvidenceReference(evidence_id=str(ref_id), kind=kind))
        contradicting_idx.append(relation == "contradicts")

    resolved = await resolve_references(session, tenant=tenant, references=supporting_refs, now=now)
    supporting: list[ResolvedEvidence] = []
    contradicting: list[ResolvedEvidence] = []
    for res, is_contra in zip(resolved.resolved, contradicting_idx, strict=False):
        (contradicting if is_contra else supporting).append(res)

    return BeliefProvenanceChain(
        belief=belief, supporting=supporting, contradicting=contradicting,
        incomplete_refs=incomplete,
    )
