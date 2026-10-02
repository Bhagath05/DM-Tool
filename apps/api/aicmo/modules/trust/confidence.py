"""Server-derived confidence (Trust Layer T0).

Authoritative confidence is an integer 0-100 computed **deterministically** from
evidence structure — band, supporting/contradicting counts, consistency,
experimental strength, claim type, and freshness. It is derived **independently
of any LLM**: a model-proposed number is recorded as diagnostic provenance only
and is *never* an input to the calculation (model-independence invariant). The
freshness decay reuses the already-audited belief resolver
(``aicmo.modules.belief.freshness.effective_confidence``) so age lowers — but
never invents — certainty.

Policy constants below are DM Tool *server policy*. They are not tuned to how
any model "sounds"; they encode how much evidence of each kind the product is
willing to let a conclusion claim.
"""

from __future__ import annotations

from datetime import datetime

from aicmo.modules.belief.freshness import effective_confidence
from aicmo.modules.trust.contracts import ConfidenceFactors
from aicmo.modules.trust.enums import ClaimType, EvidenceBand

# --- Server policy constants (not model-derived) -----------------------------

_BASE: dict[EvidenceBand, int] = {
    EvidenceBand.STRONG: 55,
    EvidenceBand.MODERATE: 40,
    EvidenceBand.WEAK: 25,
    EvidenceBand.INSUFFICIENT: 0,
}
_PER_SUPPORT = 15
_MAX_COUNTED_SUPPORT = 3
_EXPERIMENTAL_BONUS = 15
_CONSISTENCY_BONUS = 5
_PER_CONTRADICTION = 20
_MAX_COUNTED_CONTRADICTION = 2

_CEILING_BAND: dict[EvidenceBand, int | None] = {
    EvidenceBand.STRONG: 95,
    EvidenceBand.MODERATE: 75,
    EvidenceBand.WEAK: 55,
    EvidenceBand.INSUFFICIENT: None,  # insufficient evidence has no confidence
}
_FLOOR_BAND: dict[EvidenceBand, int] = {
    EvidenceBand.STRONG: 20,
    EvidenceBand.MODERATE: 10,
    EvidenceBand.WEAK: 0,
    EvidenceBand.INSUFFICIENT: 0,
}
# Claim-type ceiling. RECOMMENDATION is special: it may never exceed the
# confidence of the weakest claim that supports it (see ``recommendation_floor``).
_CEILING_TYPE: dict[ClaimType, int] = {
    ClaimType.FACT: 100,
    ClaimType.OBSERVATION: 85,
    ClaimType.INTERPRETATION: 70,
    ClaimType.HYPOTHESIS: 55,
    ClaimType.RECOMMENDATION: 100,  # overridden by supporting-claim confidence
}


def _clamp(value: int, lo: int, hi: int) -> int:
    # Ceiling always wins over floor when they cross (you can never exceed the
    # evidence/type ceiling, even if a band floor would push higher).
    lo = min(lo, hi)
    return max(lo, min(value, hi))


def derive_confidence(
    *,
    band: EvidenceBand,
    claim_type: ClaimType,
    supporting_count: int,
    contradiction_count: int = 0,
    consistent: bool = True,
    experimental: bool = False,
    reference_time: datetime | None = None,
    now: datetime | None = None,
    recommendation_support_confidence: int | None = None,
    llm_proposed: int | None = None,
) -> ConfidenceFactors:
    """Deterministically derive authoritative confidence from evidence structure.

    ``llm_proposed`` is recorded in the returned breakdown for drift analysis but
    is **never read** by the calculation. For ``claim_type == RECOMMENDATION``,
    ``recommendation_support_confidence`` caps the result at the weakest
    supporting claim's confidence (a recommendation is never more certain than
    its weakest premise).

    Gates that force the terminal INSUFFICIENT state (final = 0):
      * band is INSUFFICIENT, or
      * there is no supporting evidence (``supporting_count <= 0``).
    """
    supporting = max(0, int(supporting_count))
    contradictions = max(0, int(contradiction_count))
    reasons: list[str] = []

    # --- terminal insufficiency gates ---------------------------------------
    ceiling_band = _CEILING_BAND[band]
    if band is EvidenceBand.INSUFFICIENT or ceiling_band is None:
        reasons.append("Evidence band is insufficient; no confidence derived.")
        return ConfidenceFactors(
            band=band, claim_type=claim_type, base=0, support_contribution=0,
            consistency_contribution=0, experimental_contribution=0,
            contradiction_penalty=0, raw=0, evidence_ceiling=0, claim_ceiling=0,
            applied_ceiling=0, floor=0, derived=0, freshness_from=0, final=0,
            llm_proposed_diagnostic=llm_proposed, reasons=reasons,
        )
    if supporting <= 0:
        reasons.append("No supporting evidence; confidence cannot be established.")
        return ConfidenceFactors(
            band=band, claim_type=claim_type, base=0, support_contribution=0,
            consistency_contribution=0, experimental_contribution=0,
            contradiction_penalty=0, raw=0, evidence_ceiling=ceiling_band,
            claim_ceiling=0, applied_ceiling=0, floor=0, derived=0,
            freshness_from=0, final=0, llm_proposed_diagnostic=llm_proposed,
            reasons=reasons,
        )

    # --- additive derivation -------------------------------------------------
    base = _BASE[band]
    support_contribution = _PER_SUPPORT * min(supporting, _MAX_COUNTED_SUPPORT)
    consistency_contribution = _CONSISTENCY_BONUS if (consistent and supporting > 1) else 0
    experimental_contribution = _EXPERIMENTAL_BONUS if experimental else 0
    contradiction_penalty = _PER_CONTRADICTION * min(contradictions, _MAX_COUNTED_CONTRADICTION)

    raw = (
        base
        + support_contribution
        + consistency_contribution
        + experimental_contribution
        - contradiction_penalty
    )

    # --- ceilings + floor ----------------------------------------------------
    claim_ceiling = _CEILING_TYPE[claim_type]
    if claim_type is ClaimType.RECOMMENDATION:
        cap = 0 if recommendation_support_confidence is None else max(0, min(int(recommendation_support_confidence), 100))
        claim_ceiling = cap
        reasons.append(
            f"Recommendation capped at weakest supporting-claim confidence ({cap}%)."
        )
    applied_ceiling = min(ceiling_band, claim_ceiling)
    floor = _FLOOR_BAND[band]

    derived = _clamp(raw, floor, applied_ceiling)
    if raw > applied_ceiling:
        reasons.append(
            f"Raw {raw} exceeds the evidence/type ceiling; capped at {applied_ceiling}%."
        )
    if contradiction_penalty:
        reasons.append(
            f"{contradictions} contradiction(s) reduced confidence by {contradiction_penalty}."
        )

    # --- freshness decay (reuses the audited belief resolver) ----------------
    final, freshness_reason = effective_confidence(
        original_confidence=derived, reference_time=reference_time, now=now
    )
    if final != derived:
        reasons.append(freshness_reason)

    return ConfidenceFactors(
        band=band,
        claim_type=claim_type,
        base=base,
        support_contribution=support_contribution,
        consistency_contribution=consistency_contribution,
        experimental_contribution=experimental_contribution,
        contradiction_penalty=contradiction_penalty,
        raw=raw,
        evidence_ceiling=ceiling_band,
        claim_ceiling=claim_ceiling,
        applied_ceiling=applied_ceiling,
        floor=floor,
        derived=derived,
        freshness_from=derived,
        final=final,
        llm_proposed_diagnostic=llm_proposed,
        reasons=reasons,
    )
