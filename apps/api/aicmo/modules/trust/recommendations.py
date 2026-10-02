"""Recommendation validation (Trust Layer T0).

The decision-intelligence principle: **evidence for a claim is not evidence for
an action.** A true, well-evidenced claim does *not* automatically justify a
recommendation. Every recommendation is validated independently against:

* real supporting evidence that **bears on this action** (not merely a related
  claim),
* scope match, and absence of live contradictions,
* a consequence-appropriate confidence bar,
* and, for high-consequence actions, a verified source + mandatory human
  approval.

The result is one of the five recommendation statuses; this module never
executes anything and never lowers the approval requirement.
"""

from __future__ import annotations

from aicmo.modules.trust.contracts import CandidateRecommendation, Recommendation
from aicmo.modules.trust.enums import (
    ConsequenceLevel,
    EvidenceBand,
    ReasonCode,
    RecommendationStatus,
    SourceTier,
)

_BAND_RANK: dict[EvidenceBand, int] = {
    EvidenceBand.INSUFFICIENT: 0,
    EvidenceBand.WEAK: 1,
    EvidenceBand.MODERATE: 2,
    EvidenceBand.STRONG: 3,
}

# (minimum band, minimum confidence) the evidence must clear for each
# consequence level. HIGH additionally requires a verified source + approval.
_BARS: dict[ConsequenceLevel, tuple[EvidenceBand, int]] = {
    ConsequenceLevel.LOW: (EvidenceBand.WEAK, 40),
    ConsequenceLevel.MEDIUM: (EvidenceBand.MODERATE, 60),
    ConsequenceLevel.HIGH: (EvidenceBand.STRONG, 75),
}
_VERIFIED_SOURCES: frozenset[SourceTier] = frozenset(
    {SourceTier.VERIFIED_PROVIDER, SourceTier.FIRST_PARTY_DATA}
)


def _meets_bar(band: EvidenceBand, confidence: int, level: ConsequenceLevel) -> bool:
    min_band, min_conf = _BARS[level]
    return _BAND_RANK[band] >= _BAND_RANK[min_band] and confidence >= min_conf


def validate_recommendation(rec: CandidateRecommendation) -> Recommendation:
    """Validate a single candidate recommendation into a typed, status-bearing
    :class:`Recommendation`. Consequential actions always keep their human
    approval requirement."""
    limitations: list[str] = []
    reasons: list[ReasonCode] = []
    confidence = max(0, min(int(rec.supporting_confidence), 100))
    # MEDIUM/HIGH consequence always needs human authorization; never lowered here.
    requires_approval = rec.consequence_level is not ConsequenceLevel.LOW

    if not rec.expected_effect:
        limitations.append("No expected effect stated.")
    if rec.reversible is False:
        limitations.append("Action is not easily reversible.")
    if not rec.testable:
        limitations.append("No way to test the outcome was provided.")
    if not rec.scope_match:
        limitations.append("Supporting evidence is from a different scope than the action.")

    # 1. Live contradiction beats everything.
    if rec.contradicted:
        reasons.append(ReasonCode.CONFLICTING_EVIDENCE)
        return Recommendation(
            statement=rec.statement, consequence_level=rec.consequence_level,
            status=RecommendationStatus.CONTRADICTED, confidence=confidence,
            requires_approval=requires_approval, limitations=limitations, reasons=reasons,
        )

    # 2. Decision-intelligence gate: evidence must exist AND bear on THIS action.
    if not rec.has_supporting_evidence or not rec.bears_on_action:
        reasons.append(ReasonCode.RECOMMENDATION_EXCEEDS_EVIDENCE)
        if not rec.bears_on_action:
            limitations.append("Evidence supports a related claim, not this action.")
        return Recommendation(
            statement=rec.statement, consequence_level=rec.consequence_level,
            status=RecommendationStatus.INSUFFICIENT_EVIDENCE, confidence=confidence,
            requires_approval=requires_approval, limitations=limitations, reasons=reasons,
        )

    meets = _meets_bar(rec.band, confidence, rec.consequence_level)
    verified = any(t in _VERIFIED_SOURCES for t in rec.source_tiers)

    # 3. High-consequence actions that don't clear the bar are never silently
    #    dropped — they are routed to mandatory human review.
    if rec.consequence_level is ConsequenceLevel.HIGH and (not meets or not verified):
        if not verified:
            limitations.append("High-consequence action lacks a verified/first-party source.")
        reasons.append(ReasonCode.HIGH_CONSEQUENCE_UNDER_EVIDENCED)
        return Recommendation(
            statement=rec.statement, consequence_level=rec.consequence_level,
            status=RecommendationStatus.HIGH_RISK_REQUIRES_REVIEW, confidence=confidence,
            requires_approval=True, limitations=limitations, reasons=reasons,
        )

    # 4. Under the evidence bar for its consequence → insufficient.
    if not meets:
        reasons.append(ReasonCode.RECOMMENDATION_EXCEEDS_EVIDENCE)
        return Recommendation(
            statement=rec.statement, consequence_level=rec.consequence_level,
            status=RecommendationStatus.INSUFFICIENT_EVIDENCE, confidence=confidence,
            requires_approval=requires_approval, limitations=limitations, reasons=reasons,
        )

    # 5. Meets the bar. SUPPORTED only when nothing qualifies it; else QUALIFIED.
    status = RecommendationStatus.QUALIFIED if limitations else RecommendationStatus.SUPPORTED
    return Recommendation(
        statement=rec.statement, consequence_level=rec.consequence_level,
        status=status, confidence=confidence, requires_approval=requires_approval,
        limitations=limitations, reasons=reasons,
    )
