"""Scaling Intelligence — Phase 9.1.5 layer 4.

Two cards from a single CSV upload:

  - scale_candidate   creative whose CPL is ≤ 75% of the brand average
                      AND sample is sufficient AND it hasn't already
                      consumed a disproportionate share of the budget
                      (so there's room to scale).

  - budget_waste      creative whose CPL is ≥ 1.5× the brand average
                      AND has consumed a meaningful chunk of spend.

Saturation / fatigue are deliberately NOT in 9.1.5 — they need
multi-upload time-series. Approved deferral to 9.1.6.

Confidence cap is 80 (one band below winners) because these cards
are prescriptive about money.
"""

from __future__ import annotations

from aicmo.modules.performance.schemas import (
    CreativeRollup,
    DiagnosticDraft,
)

# Confidence cap (approved in plan)
_CONFIDENCE_CAP = 80


def summarise_scale_candidates(
    rollups: list[CreativeRollup],
) -> list[DiagnosticDraft]:
    """Surface the single best scale-up candidate. Returns 0 or 1 draft."""
    sufficient = [r for r in rollups if r.sample_state == "sufficient" and r.cpl is not None]
    if len(sufficient) < 2:
        return []

    total_spend = sum(r.spend for r in sufficient)
    total_conv = sum(r.conversions for r in sufficient)
    if total_conv == 0:
        return []

    brand_cpl = total_spend / total_conv

    # Candidate must beat the brand average by ≥ 25%.
    candidates = [
        r for r in sufficient if r.cpl is not None and r.cpl <= brand_cpl * 0.75
    ]
    if not candidates:
        return []

    # And it should have HEADROOM — already-dominant creatives
    # (>50% of total spend) aren't "scale candidates", they're
    # already scaled. Recommendation in that case is "duplicate
    # into new audience" which the existing winner card already
    # covers in 9.1.
    candidates = [r for r in candidates if r.spend <= total_spend * 0.5]
    if not candidates:
        return []

    # Pick the one with the best CPL.
    candidate = min(candidates, key=lambda r: r.cpl)  # type: ignore[arg-type, return-value]

    # Confidence: base 65, +sample, capped at 80.
    conf = 65
    if candidate.conversions >= 50:
        conf += 15
    elif candidate.conversions >= 20:
        conf += 10
    elif candidate.conversions >= 5:
        conf += 5
    conf = min(conf, _CONFIDENCE_CAP)
    if conf < 40:
        return []

    # Project the lift if we doubled this creative's spend at its
    # current cost-per-lead. Honest — it's an upper-bound estimate.
    extra_leads = int(candidate.spend / candidate.cpl) if candidate.cpl else 0  # noqa: F841

    return [
        DiagnosticDraft(
            kind="scale_candidate",
            impact_category="lead",
            confidence=conf,
            subject_creative_ref=candidate.creative_ref,
            evidence={
                "creative_ref": candidate.creative_ref,
                "platform": candidate.platform,
                "cpl": candidate.cpl,
                "brand_avg_cpl": brand_cpl,
                "cpl_advantage_ratio": brand_cpl / candidate.cpl,
                "spend": candidate.spend,
                "currency": candidate.currency,
                "conversions": candidate.conversions,
                "headroom_share": 1.0 - (candidate.spend / total_spend),
                "concept_family": candidate.concept_family,
                "audience": candidate.audience,
            },
        )
    ]


def summarise_budget_waste(
    rollups: list[CreativeRollup],
) -> list[DiagnosticDraft]:
    """Surface the single worst budget-waster. Returns 0 or 1 draft."""
    sufficient = [r for r in rollups if r.sample_state == "sufficient" and r.cpl is not None]
    if len(sufficient) < 2:
        return []

    total_spend = sum(r.spend for r in sufficient)
    total_conv = sum(r.conversions for r in sufficient)
    if total_conv == 0:
        return []

    brand_cpl = total_spend / total_conv

    # Waste candidate: CPL ≥ 1.5× brand average AND spend ≥ 10%
    # of total (otherwise it's a small experiment, not waste).
    wasters = [
        r
        for r in sufficient
        if r.cpl is not None
        and r.cpl >= brand_cpl * 1.5
        and r.spend >= total_spend * 0.1
    ]
    if not wasters:
        return []

    waster = max(wasters, key=lambda r: r.spend)

    conf = 65
    if waster.conversions >= 20:
        conf += 10
    elif waster.conversions >= 5:
        conf += 5
    # Bigger ratio = more confident waste call.
    if waster.cpl >= brand_cpl * 2.5:  # type: ignore[operator]
        conf += 5
    conf = min(conf, _CONFIDENCE_CAP)
    if conf < 40:
        return []

    # Estimate freed leads if we reallocated waster's spend at brand CPL.
    freed_leads = int(waster.spend / brand_cpl) - waster.conversions
    if freed_leads < 0:
        freed_leads = 0

    return [
        DiagnosticDraft(
            kind="budget_waste",
            impact_category="cost",
            confidence=conf,
            subject_creative_ref=waster.creative_ref,
            evidence={
                "creative_ref": waster.creative_ref,
                "platform": waster.platform,
                "cpl": waster.cpl,
                "brand_avg_cpl": brand_cpl,
                "cpl_overrun_ratio": waster.cpl / brand_cpl if brand_cpl else None,  # type: ignore[operator]
                "spend": waster.spend,
                "currency": waster.currency,
                "conversions": waster.conversions,
                "spend_share": waster.spend / total_spend,
                "freed_leads_estimate": freed_leads,
            },
        )
    ]
