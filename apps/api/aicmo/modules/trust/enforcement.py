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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.trust.enums import ClaimStatus, RecommendationStatus
from aicmo.modules.trust.shadow import ShadowResult

# Mirrors the agent response's coarse evidence-status literal (kept here so the
# Trust layer never imports the agent package).
EvidenceStatusLiteral = Literal["ok", "INSUFFICIENT_EVIDENCE"]


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
    requires_approval: bool
    safe_language: str


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
    recommendations: list[SafeRecommendation] = Field(default_factory=list)
    enforced: bool = True
    degraded: bool = False  # True when fail-safe degradation was applied


class EnforcedResponse(BaseModel):
    """What the runtime applies to the user-visible AgentResponse."""

    model_config = ConfigDict(extra="forbid")

    confidence: int  # server-authoritative; NEVER the LLM value
    evidence_status: EvidenceStatusLiteral  # legacy coarse field
    envelope: TrustEnvelope
    answer_suffix: str | None = None  # deterministic authoritative note, or None


def _overall_status(shadow: ShadowResult) -> EnforcedStatus:
    claims = shadow.trust.claims
    claim = claims[0] if claims else None
    causal_downgraded = any(a.downgraded for a in shadow.trust.causal_assessments)
    if claim is None or claim.status is ClaimStatus.INSUFFICIENT:
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
            requires_approval=r.requires_approval,
            safe_language=_SAFE_LANGUAGE[_REC_STATUS_MAP.get(r.status, EnforcedStatus.INSUFFICIENT_EVIDENCE)],
        )
        for r in shadow.trust.recommendations
    ]

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
        recommendations=safe_recs,
        enforced=True,
        degraded=False,
    )
    return EnforcedResponse(
        confidence=server_confidence,
        evidence_status=evidence_status,
        envelope=envelope,
        answer_suffix=answer_suffix,
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
