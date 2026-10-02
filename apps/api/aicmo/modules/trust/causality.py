"""Causal-claim evidence gate (Trust Layer T0).

Correlation is not causation. A claim phrased causally ("X *caused* / *drove* /
*led to* Y") may only stand as causal when it rests on an experimental design
strong enough to support it. The *level* of evidence is taken from structured
metadata (which design produced the finding), never inferred from the wording —
keyword detection is used only as a conservative *supplement* to catch causal
phrasing the caller did not flag, and it can only make the gate *stricter*,
never weaker.

Honest current capability: DM Tool's own pipelines today reach at most
``QUASI_EXPERIMENTAL`` (e.g. advisor outcome analysis, creative evaluation).
``CONTROLLED_EXPERIMENT`` and ``RANDOMIZED`` are defined on the ladder for
correctness but are **not currently produced** by the platform, so in practice
causal phrasing is downgraded to association/observation today.
"""

from __future__ import annotations

from collections.abc import Iterable

from aicmo.modules.trust.contracts import CausalAssessment
from aicmo.modules.trust.enums import CausalLevel, ReasonCode, SourceTier
from aicmo.modules.trust.sources import can_back_causal

# The strongest causal design DM Tool can honestly produce today.
CURRENT_MAX_CAPABILITY: CausalLevel = CausalLevel.QUASI_EXPERIMENTAL
_UNAVAILABLE_TODAY: frozenset[CausalLevel] = frozenset(
    {CausalLevel.CONTROLLED_EXPERIMENT, CausalLevel.RANDOMIZED}
)
# Levels at which bare causal language is permitted.
_CAUSAL_PERMITTED_AT: frozenset[CausalLevel] = frozenset(
    {CausalLevel.CONTROLLED_EXPERIMENT, CausalLevel.RANDOMIZED}
)

# Conservative causal-language markers. Presence promotes a statement to a
# causal *candidate*; it never establishes the evidence level.
_CAUSAL_MARKERS: tuple[str, ...] = (
    "caused", "causes", "causing", "because of", "due to", "drove", "drives",
    "driving", "led to", "leads to", "leading to", "resulted in", "results in",
    "responsible for", "made ", "makes ", "thanks to", "as a result of",
    "boosted", "increased sales by causing", "directly increased",
)


def looks_causal(statement: str) -> bool:
    """Conservative keyword scan — a *supplement* for unflagged causal phrasing,
    not the authority on whether a claim is causal."""
    text = f" {statement.lower()} "
    return any(marker in text for marker in _CAUSAL_MARKERS)


def _association_phrasing(statement: str, level: CausalLevel) -> str:
    if level is CausalLevel.QUASI_EXPERIMENTAL:
        return (
            "Evidence from a quasi-experiment suggests this likely contributed, "
            "but this is not a controlled experiment."
        )
    if level is CausalLevel.ASSOCIATIONAL:
        return "This is associated with the outcome; a causal link is not established."
    return "This was observed alongside the outcome; no causal link is established."


def assess_causality(
    *,
    statement: str,
    evidence_level: CausalLevel = CausalLevel.OBSERVATIONAL,
    is_causal_candidate: bool | None = None,
    source_tiers: Iterable[SourceTier] = (),
) -> CausalAssessment:
    """Assess whether a statement may stand as a causal claim.

    ``is_causal_candidate`` is the caller's structured flag; when ``None`` we
    fall back to the conservative keyword scan. A statement flagged *or*
    detected as causal is treated as a candidate (detection can only tighten).
    """
    tiers = list(source_tiers)
    detected = looks_causal(statement)
    candidate = detected if is_causal_candidate is None else (is_causal_candidate or detected)

    if not candidate:
        return CausalAssessment(
            statement=statement, is_causal_candidate=False,
            evidence_level=evidence_level, permitted=True, downgraded=False,
        )

    # A causal claim needs grounding data at all.
    if tiers and not can_back_causal(tiers):
        return CausalAssessment(
            statement=statement, is_causal_candidate=True,
            evidence_level=evidence_level, permitted=False, downgraded=True,
            suggested_statement=_association_phrasing(statement, evidence_level),
            disclosure="No observed data backs this causal claim; downgraded.",
            reason_code=ReasonCode.UNSUPPORTED_CAUSAL_CLAIM,
        )

    if evidence_level in _CAUSAL_PERMITTED_AT:
        disclosure = None
        if evidence_level in _UNAVAILABLE_TODAY:
            disclosure = (
                f"Stated at {evidence_level.value}, which exceeds DM Tool's current "
                f"capability ({CURRENT_MAX_CAPABILITY.value}); verify the design."
            )
        return CausalAssessment(
            statement=statement, is_causal_candidate=True,
            evidence_level=evidence_level, permitted=True, downgraded=False,
            disclosure=disclosure,
        )

    # Not strong enough — downgrade causal phrasing to association/observation.
    reason = (
        ReasonCode.CAUSAL_SCOPE_EXCEEDED
        if evidence_level is CausalLevel.QUASI_EXPERIMENTAL
        else ReasonCode.UNSUPPORTED_CAUSAL_CLAIM
    )
    return CausalAssessment(
        statement=statement, is_causal_candidate=True,
        evidence_level=evidence_level, permitted=False, downgraded=True,
        suggested_statement=_association_phrasing(statement, evidence_level),
        disclosure=(
            f"Evidence is {evidence_level.value}; causal language requires a "
            f"controlled or randomized design."
        ),
        reason_code=reason,
    )
