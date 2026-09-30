"""Deterministic, evidence-derived confidence.

Confidence is NEVER "the LLM sounds sure". It is a pure function of the
structured evidence: how many pieces support vs. contradict the belief, and
whether any supporting evidence is experimental (a measured outcome) rather than
merely observational. The service uses this to set confidence + status; a raw
LLM/caller-supplied number is ignored (at most clamped down to this ceiling).
"""

from __future__ import annotations

from aicmo.modules.belief.enums import BeliefStatus

# Tunables — explainable, not magic. No belief ever reaches 100 (no certainty).
_BASE = 25
_PER_SUPPORT = 15
_MAX_COUNTED_SUPPORT = 3
_EXPERIMENTAL_BONUS = 15
_PER_CONTRADICTION = 20
_CEILING = 95


def derive_confidence(*, supports: int, contradicts: int, experimental: bool) -> tuple[int, str]:
    """Return (confidence 0-100, human reason). 0 supports → 0 (unvalidated)."""
    if supports <= 0:
        return 0, "No supporting evidence — unvalidated, not established fact."
    counted = min(supports, _MAX_COUNTED_SUPPORT)
    value = _BASE + _PER_SUPPORT * counted
    if experimental:
        value += _EXPERIMENTAL_BONUS
    value -= _PER_CONTRADICTION * min(contradicts, 2)
    value = max(0, min(value, _CEILING))
    kind = "experimental (measured outcome)" if experimental else "observational"
    reason = (
        f"{supports} supporting ({kind}) and {contradicts} contradicting piece(s) "
        f"of evidence → confidence {value}."
    )
    return value, reason


def derive_status(*, supports: int, contradicts: int) -> BeliefStatus:
    """A belief cannot be ACTIVE without supporting evidence, and becomes
    CONTRADICTED when contradictions meet or exceed support."""
    if supports <= 0:
        return BeliefStatus.UNVALIDATED
    if contradicts > 0 and contradicts >= supports:
        return BeliefStatus.CONTRADICTED
    return BeliefStatus.ACTIVE
