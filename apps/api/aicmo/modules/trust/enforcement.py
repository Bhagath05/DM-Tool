"""Trust enforcement (T3) — the server becomes the authority over what the
user-visible response may claim.

T2 observed and discarded. T3 takes the same deterministic shadow result and
*enforces* it: the user-visible confidence and evidence status are replaced with
server-derived values, unsupported causal wording is corrected with an
authoritative note, mixed/insufficient evidence is surfaced honestly, and
high-consequence recommendations stay review-gated. The LLM is never the final
authority.

Enforcement is **structured**, not a brittle natural-language rewriter: it
corrects trust-sensitive metadata and attaches authoritative, deterministic
presentation-safe language. It is also **fail-safe** — if validation errors,
the trust-sensitive output degrades to ``INSUFFICIENT_EVIDENCE`` (never a
preserved high-confidence claim), while unrelated answer text is kept.

This module performs no I/O, executes nothing, approves nothing, and exposes no
chain-of-thought — only fixed safe strings and server-derived numbers.
"""

from __future__ import annotations

import enum
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.trust.contracts import Claim, MetricResult
from aicmo.modules.trust.enums import ClaimStatus, ClaimType, RecommendationStatus, SourceTier
from aicmo.modules.trust.shadow import ShadowResult

# Mirrors the agent response's coarse evidence-status literal (kept here so the
# Trust layer never imports the agent package).
EvidenceStatusLiteral = Literal["ok", "INSUFFICIENT_EVIDENCE"]

# The runtime's synthetic "overall answer" claim (used to derive a turn-level
# confidence from the verified evidence base). It drives the overall verdict but
# is never shown to the user as an individual claim.
SYNTHETIC_ANSWER_CLAIM = "turn answer"

# User-facing provenance labels. NOT a universal quality ranking — they describe
# where information came from. MODEL_INFERENCE / UNKNOWN must never read as
# verified first-party data.
_SOURCE_LABEL: dict[SourceTier, str] = {
    SourceTier.VERIFIED_PROVIDER: "Verified",
    SourceTier.FIRST_PARTY_DATA: "First-party data",
    SourceTier.USER_PROVIDED: "User-provided",
    SourceTier.DERIVED_INTERNAL: "Derived",
    SourceTier.RESEARCH: "Research",
    SourceTier.MODEL_INFERENCE: "AI inference",
    SourceTier.UNKNOWN: "Unknown",
}
# Grounding tiers (real observed data) ranked strongest→weakest for picking the
# label that best describes what actually backs a claim.
_GROUNDING_ORDER: tuple[SourceTier, ...] = (
    SourceTier.VERIFIED_PROVIDER,
    SourceTier.FIRST_PARTY_DATA,
    SourceTier.USER_PROVIDED,
    SourceTier.DERIVED_INTERNAL,
    SourceTier.RESEARCH,
)
# Defense-in-depth: redact secret-like values before surfacing any model-authored
# claim text to the user (high-signal shapes only, to avoid false positives on
# ordinary marketing prose). Mirrors the belief layer's scrubber.
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|AKIA[0-9A-Z]{12,}|xox[bap]-[a-z0-9-]{10,}|-----BEGIN|"
    r"(api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret|smtp[_-]?password|password)"
    r"\s*[:=]\s*\S+|bearer\s+[a-z0-9._-]{20,})"
)


def _scrub(text: str) -> str:
    return _SECRET_RE.sub("[redacted]", text)


# Claim types whose user-facing wording must stay cautious.
_CLAIM_TYPE_LABEL: dict[ClaimType, str] = {
    ClaimType.FACT: "Verified fact",
    ClaimType.OBSERVATION: "Observation",
    ClaimType.INTERPRETATION: "Interpretation",
    ClaimType.HYPOTHESIS: "Hypothesis to test",
    ClaimType.RECOMMENDATION: "Recommendation",
}


class EnforcedStatus(enum.StrEnum):
    """The authoritative, presentation-safe outcome for a conclusion/action."""

    SUPPORTED = "supported"
    QUALIFIED = "qualified"
    DOWNGRADED = "downgraded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTRADICTED = "contradicted"
    MIXED_EVIDENCE = "mixed_evidence"
    HIGH_RISK_REQUIRES_REVIEW = "high_risk_requires_review"


# Deterministic, user-facing language. No implementation jargon, no enum names,
# no numbers that could imply false precision — just an honest sentence.
_SAFE_LANGUAGE: dict[EnforcedStatus, str] = {
    EnforcedStatus.SUPPORTED: "The available verified evidence supports this conclusion.",
    EnforcedStatus.QUALIFIED: "The available evidence supports this conclusion with important limitations.",
    EnforcedStatus.DOWNGRADED: "Some statements were adjusted to match what the evidence actually supports.",
    EnforcedStatus.INSUFFICIENT_EVIDENCE: "I don't have enough verified evidence to make this conclusion.",
    EnforcedStatus.CONTRADICTED: "The available evidence conflicts with this conclusion, so I can't present it as supported.",
    EnforcedStatus.MIXED_EVIDENCE: "The available evidence points in different directions, so I can't make a single confident conclusion.",
    EnforcedStatus.HIGH_RISK_REQUIRES_REVIEW: "This recommendation has meaningful consequences and the available evidence is not strong enough to treat it as a routine recommendation.",
}

_REC_STATUS_MAP: dict[RecommendationStatus, EnforcedStatus] = {
    RecommendationStatus.SUPPORTED: EnforcedStatus.SUPPORTED,
    RecommendationStatus.QUALIFIED: EnforcedStatus.QUALIFIED,
    RecommendationStatus.INSUFFICIENT_EVIDENCE: EnforcedStatus.INSUFFICIENT_EVIDENCE,
    RecommendationStatus.CONTRADICTED: EnforcedStatus.CONTRADICTED,
    RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW: EnforcedStatus.HIGH_RISK_REQUIRES_REVIEW,
}

# Statuses that warrant an authoritative user-facing note appended to the answer.
_NOTE_STATUSES = frozenset({
    EnforcedStatus.INSUFFICIENT_EVIDENCE,
    EnforcedStatus.CONTRADICTED,
    EnforcedStatus.MIXED_EVIDENCE,
    EnforcedStatus.DOWNGRADED,
})


class SafeRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    status: EnforcedStatus
    consequence: str  # low | medium | high
    requires_approval: bool
    safe_language: str


class ClaimView(BaseModel):
    """One server-validated claim, presentation-ready. The status/confidence/
    type are server-derived; the UI only renders them."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    claim_type: ClaimType
    claim_type_label: str
    trust_status: EnforcedStatus
    confidence: int
    source: str  # user-facing provenance label (e.g. "First-party data")
    causal_level: str | None = None
    evidence_labels: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    safe_language: str


class MetricView(BaseModel):
    """A metric rendered only from a deterministic registry result. An invalid
    metric is NOT_COMPUTABLE — never a fabricated number."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: float | None
    unit: str
    computable: bool
    status: str  # "ok" | "not_computable"
    reason: str | None = None
    source: str


class TrustSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: int = 0
    qualified: int = 0
    downgraded: int = 0
    insufficient: int = 0
    contradicted: int = 0
    mixed: int = 0
    not_computable_metrics: int = 0
    high_risk_recommendations: int = 0


class TrustEnvelope(BaseModel):
    """The authoritative, user-facing trust verdict attached to a response.
    Server-derived; carries only safe fixed language + numbers (no secrets, no
    chain-of-thought, no raw model text)."""

    model_config = ConfigDict(extra="forbid")

    status: EnforcedStatus
    safe_language: str
    server_confidence: int
    verdict: str  # TrustVerdict value, for operators/audit
    disclosures: list[str] = Field(default_factory=list)
    claims: list[ClaimView] = Field(default_factory=list)
    metrics: list[MetricView] = Field(default_factory=list)
    recommendations: list[SafeRecommendation] = Field(default_factory=list)
    summary: TrustSummary = Field(default_factory=TrustSummary)
    enforced: bool = True
    degraded: bool = False  # True when fail-safe degradation was applied


class EnforcedResponse(BaseModel):
    """What the runtime applies to the user-visible AgentResponse."""

    model_config = ConfigDict(extra="forbid")

    confidence: int  # server-authoritative; NEVER the LLM value
    evidence_status: EvidenceStatusLiteral  # legacy coarse field
    envelope: TrustEnvelope
    answer_suffix: str | None = None  # deterministic authoritative note, or None


def _downgraded_causal_statements(shadow: ShadowResult) -> set[str]:
    """Statements whose causal claim the server downgraded. Causal assessments
    carry the originating statement, so this matches back to the right claim —
    a single causal overclaim never downgrades the turn's other claims."""
    return {a.statement for a in shadow.trust.causal_assessments if a.downgraded}


def _claim_status(claim: Claim, *, causal_downgraded: bool) -> EnforcedStatus:
    if claim.status is ClaimStatus.INSUFFICIENT:
        return EnforcedStatus.INSUFFICIENT_EVIDENCE
    if claim.status is ClaimStatus.CONTRADICTED:
        return EnforcedStatus.CONTRADICTED
    if claim.status is ClaimStatus.MIXED:
        return EnforcedStatus.MIXED_EVIDENCE
    if causal_downgraded:
        return EnforcedStatus.DOWNGRADED
    if claim.limitations:
        return EnforcedStatus.QUALIFIED
    return EnforcedStatus.SUPPORTED


# Worst→best precedence for rolling many claim statuses into one turn verdict.
_STATUS_RANK: dict[EnforcedStatus, int] = {
    EnforcedStatus.CONTRADICTED: 0,
    EnforcedStatus.INSUFFICIENT_EVIDENCE: 1,
    EnforcedStatus.MIXED_EVIDENCE: 2,
    EnforcedStatus.DOWNGRADED: 3,
    EnforcedStatus.QUALIFIED: 4,
    EnforcedStatus.SUPPORTED: 5,
}


def _overall_status(shadow: ShadowResult) -> EnforcedStatus:
    """Roll all claims into one turn-level verdict (weakest claim dominates)."""
    claims = shadow.trust.claims
    if not claims:
        return EnforcedStatus.INSUFFICIENT_EVIDENCE
    downgraded = _downgraded_causal_statements(shadow)
    per_claim = [
        _claim_status(c, causal_downgraded=c.statement in downgraded) for c in claims
    ]
    overall = min(per_claim, key=lambda s: _STATUS_RANK[s])
    # A causal overclaim anywhere in the turn (including one in the free-text
    # observations that matches no specific claim) means the answer carries
    # unsupported causal language → cap the TURN verdict at DOWNGRADED, even
    # though individual factual claims are not themselves downgraded.
    if downgraded and _STATUS_RANK[overall] > _STATUS_RANK[EnforcedStatus.DOWNGRADED]:
        overall = EnforcedStatus.DOWNGRADED
    return overall


def _source_label(tiers: list[SourceTier]) -> str:
    """The provenance label that best describes what actually backs a claim:
    the strongest grounding (real-data) tier, else the non-grounding tier present
    (so an inference-only claim never reads as verified)."""
    for tier in _GROUNDING_ORDER:
        if tier in tiers:
            return _SOURCE_LABEL[tier]
    for tier in (SourceTier.MODEL_INFERENCE, SourceTier.UNKNOWN):
        if tier in tiers:
            return _SOURCE_LABEL[tier]
    return _SOURCE_LABEL[SourceTier.UNKNOWN]


def _friendly_evidence_labels(evidence_ids: list[str]) -> list[str]:
    """Human-readable evidence labels for the 'why' disclosure — never raw ids.
    A tool read shows the tool name; a belief shows 'belief memory'."""
    out: list[str] = []
    for eid in evidence_ids:
        label = eid[5:] if eid.startswith("tool:") else "belief memory"
        if label and label not in out:
            out.append(label)
    return out


def _claim_view(claim: Claim, *, causal_downgraded: bool) -> ClaimView:
    status = _claim_status(claim, causal_downgraded=causal_downgraded)
    confidence = claim.confidence if status in _CONFIDENT_STATUSES else 0
    return ClaimView(
        statement=_scrub(claim.statement),
        claim_type=claim.claim_type,
        claim_type_label=_CLAIM_TYPE_LABEL[claim.claim_type],
        trust_status=status,
        confidence=confidence,
        source=_source_label(claim.source_tiers),
        causal_level=claim.causal_level.value if claim.causal_level is not None else None,
        evidence_labels=_friendly_evidence_labels(claim.evidence_ids),
        limitations=list(claim.limitations),
        safe_language=_SAFE_LANGUAGE[status],
    )


def _metric_view(m: MetricResult) -> MetricView:
    return MetricView(
        name=m.name,
        value=m.value if m.computable else None,
        unit=m.unit,
        computable=m.computable,
        status="ok" if m.computable else "not_computable",
        reason=None if m.computable else "Required inputs could not be verified.",
        source=_SOURCE_LABEL.get(m.source_tier, _SOURCE_LABEL[SourceTier.UNKNOWN]),
    )


def _disclosures(shadow: ShadowResult, status: EnforcedStatus) -> list[str]:
    out: list[str] = []
    # Causal corrections use the fixed honest rephrase — never the raw model text.
    for a in shadow.trust.causal_assessments:
        if a.downgraded:
            correction = a.suggested_statement or a.disclosure
            if correction and correction not in out:
                out.append(correction)
    # A metric that could not be verified is named, not silently dropped.
    for m in shadow.trust.metric_results:
        if not m.computable:
            note = f"A requested metric ({m.name}) could not be verified from the data and is not shown as a number."
            if note not in out:
                out.append(note)
    return out


_CONFIDENT_STATUSES = frozenset({
    EnforcedStatus.SUPPORTED,
    EnforcedStatus.QUALIFIED,
    EnforcedStatus.DOWNGRADED,
})


def enforce(shadow: ShadowResult) -> EnforcedResponse:
    """Turn a deterministic shadow result into the enforced, server-authoritative
    user-visible outcome. Confidence is always server-derived — never the LLM's."""
    status = _overall_status(shadow)
    # Honor the model's OWN disclaimer: if the LLM declared insufficient evidence,
    # the server never upgrades that to a confident answer (more conservative is
    # always safe). The reverse — LLM 'ok' but server insufficient — is already a
    # downgrade handled by _overall_status.
    if shadow.llm_evidence_status == "INSUFFICIENT_EVIDENCE" and status in _CONFIDENT_STATUSES:
        status = EnforcedStatus.INSUFFICIENT_EVIDENCE

    # Confidence is shown only for genuinely supported conclusions, and is the
    # server-derived value (never the LLM's). Everything else shows no number.
    server_confidence = shadow.server_confidence if status in _CONFIDENT_STATUSES else 0
    evidence_status = (
        "INSUFFICIENT_EVIDENCE"
        if status in (EnforcedStatus.INSUFFICIENT_EVIDENCE, EnforcedStatus.CONTRADICTED)
        else "ok"
    )

    disclosures = _disclosures(shadow, status)
    safe_recs = [
        SafeRecommendation(
            action=r.statement,
            status=_REC_STATUS_MAP.get(r.status, EnforcedStatus.INSUFFICIENT_EVIDENCE),
            consequence=r.consequence_level.value,
            requires_approval=r.requires_approval,
            safe_language=_SAFE_LANGUAGE[_REC_STATUS_MAP.get(r.status, EnforcedStatus.INSUFFICIENT_EVIDENCE)],
        )
        for r in shadow.trust.recommendations
    ]

    # Per-claim views — but never surface the synthetic overall "turn answer"
    # claim as an individual claim (it only drives the turn-level verdict).
    downgraded = _downgraded_causal_statements(shadow)
    claim_views = [
        _claim_view(c, causal_downgraded=c.statement in downgraded)
        for c in shadow.trust.claims
        if c.statement != SYNTHETIC_ANSWER_CLAIM
    ]
    metric_views = [_metric_view(m) for m in shadow.trust.metric_results]
    summary = _summary(claim_views, metric_views, safe_recs)

    # Build an authoritative, clearly delimited note (deterministic — not a
    # rewrite of the model's prose) for the trust-sensitive cases.
    note_lines: list[str] = []
    if status in _NOTE_STATUSES:
        note_lines.append(_SAFE_LANGUAGE[status])
    note_lines.extend(disclosures)
    if any(r.status is EnforcedStatus.HIGH_RISK_REQUIRES_REVIEW for r in safe_recs):
        note_lines.append(_SAFE_LANGUAGE[EnforcedStatus.HIGH_RISK_REQUIRES_REVIEW])
    answer_suffix = "\n\n_Note on evidence:_\n" + "\n".join(note_lines) if note_lines else None

    envelope = TrustEnvelope(
        status=status,
        safe_language=_SAFE_LANGUAGE[status],
        server_confidence=server_confidence,
        verdict=shadow.trust.verdict.value,
        disclosures=disclosures,
        claims=claim_views,
        metrics=metric_views,
        recommendations=safe_recs,
        summary=summary,
        enforced=True,
        degraded=False,
    )
    return EnforcedResponse(
        confidence=server_confidence,
        evidence_status=evidence_status,
        envelope=envelope,
        answer_suffix=answer_suffix,
    )


def _summary(
    claims: list[ClaimView], metrics: list[MetricView], recs: list[SafeRecommendation]
) -> TrustSummary:
    def _n(status: EnforcedStatus) -> int:
        return sum(1 for c in claims if c.trust_status is status)

    return TrustSummary(
        supported=_n(EnforcedStatus.SUPPORTED),
        qualified=_n(EnforcedStatus.QUALIFIED),
        downgraded=_n(EnforcedStatus.DOWNGRADED),
        insufficient=_n(EnforcedStatus.INSUFFICIENT_EVIDENCE),
        contradicted=_n(EnforcedStatus.CONTRADICTED),
        mixed=_n(EnforcedStatus.MIXED_EVIDENCE),
        not_computable_metrics=sum(1 for m in metrics if not m.computable),
        high_risk_recommendations=sum(
            1 for r in recs if r.status is EnforcedStatus.HIGH_RISK_REQUIRES_REVIEW
        ),
    )


def fail_safe() -> EnforcedResponse:
    """Fail-SAFE degradation: used when validation errors unexpectedly. Never
    preserves an unsupported high-confidence claim — trust-sensitive output
    becomes INSUFFICIENT_EVIDENCE with zero server confidence."""
    status = EnforcedStatus.INSUFFICIENT_EVIDENCE
    envelope = TrustEnvelope(
        status=status,
        safe_language=_SAFE_LANGUAGE[status],
        server_confidence=0,
        verdict="insufficient_evidence",
        disclosures=[],
        recommendations=[],
        enforced=True,
        degraded=True,
    )
    return EnforcedResponse(
        confidence=0,
        evidence_status="INSUFFICIENT_EVIDENCE",
        envelope=envelope,
        answer_suffix="\n\n_Note on evidence:_\n" + _SAFE_LANGUAGE[status],
    )
