"""Offer Intelligence — Phase 9.1.5 layer 3.

Two cards:

  - offer_winner               which offer_type tag converts best
                               (ranked by conversion rate, not CPL,
                               because the offer changes both the
                               buying threshold AND the cost; CVR is
                               the cleanest signal we have).

  - offer_pricing_sensitivity  discount vs no-discount comparison.
                               Approved narrow scope: only fires when
                               there are ≥3 creatives on each side and
                               one side is materially better. We never
                               claim "pricing sensitivity" off a single
                               creative.
"""

from __future__ import annotations

from aicmo.modules.performance.intelligence._grouping import (
    GroupAggregate,
    aggregate,
    group_by,
    group_confidence,
    keep_sufficient,
)
from aicmo.modules.performance.schemas import (
    CreativeRollup,
    DiagnosticDraft,
)


def summarise_offers(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    groups = group_by(rollups, key_fn=lambda r: r.offer_type)
    aggregates = {k: aggregate(k, members) for k, members in groups.items()}
    eligible = keep_sufficient(aggregates)
    if len(eligible) < 2:
        return []

    # Rank by CVR (conversion rate). Higher is better.
    # Filter out groups with zero clicks — can't compute CVR.
    ranked = sorted(
        [g for g in eligible if g.clicks > 0],
        key=lambda g: g.cvr,
        reverse=True,
    )
    if len(ranked) < 2:
        return []

    winner = ranked[0]
    runner_up = ranked[1]
    # Use CVR margin for confidence.
    conf = group_confidence(
        winner, runner_up=runner_up, margin_metric="cvr"
    )
    if conf < 40:
        return []

    return [
        DiagnosticDraft(
            kind="offer_winner",
            impact_category=(
                "revenue" if winner.conversion_value > 0 else "lead"
            ),
            confidence=conf,
            subject_creative_ref=str(winner.key),
            evidence={
                "offer_type": winner.key,
                "creatives_count": winner.creatives_count,
                "creative_refs": winner.creative_refs,
                "clicks": winner.clicks,
                "conversions": winner.conversions,
                "cvr": winner.cvr,
                "spend": winner.spend,
                "currency": winner.currency,
                "runner_up_offer": str(runner_up.key),
                "runner_up_cvr": runner_up.cvr,
                "cvr_ratio": (
                    winner.cvr / runner_up.cvr if runner_up.cvr else None
                ),
                "field_size": len(ranked),
            },
        )
    ]


def summarise_pricing_sensitivity(
    rollups: list[CreativeRollup],
) -> list[DiagnosticDraft]:
    """Discount-on vs discount-off only. Narrow by design."""
    # Bucket: anything offer_type == "discount" or "promotion" is
    # discount-on; "none" is discount-off; other offers are excluded
    # so we don't confuse the comparison (free_trial / consultation
    # are their own category and shouldn't be folded in).
    on_members = [r for r in rollups if r.offer_type in ("discount", "promotion")]
    off_members = [r for r in rollups if r.offer_type == "none"]

    # Approved threshold: ≥3 creatives per side.
    if len(on_members) < 3 or len(off_members) < 3:
        return []

    on = aggregate("discount_on", on_members)
    off = aggregate("discount_off", off_members)
    if on.sample_state != "sufficient" or off.sample_state != "sufficient":
        return []
    if on.cvr == 0 and off.cvr == 0:
        return []

    # Determine the better side by CVR.
    if on.cvr >= off.cvr:
        better, worse, side = on, off, "discount_on"
    else:
        better, worse, side = off, on, "discount_off"

    # Require a meaningful gap — 1.3× — before claiming sensitivity.
    if worse.cvr == 0 or better.cvr / worse.cvr < 1.3:
        return []

    # Approved confidence cap: 80.
    conf = group_confidence(
        better, runner_up=worse, margin_metric="cvr", cap=80
    )
    if conf < 40:
        return []

    return [
        DiagnosticDraft(
            kind="offer_pricing_sensitivity",
            impact_category="revenue" if better.conversion_value > 0 else "lead",
            confidence=conf,
            subject_creative_ref=side,
            evidence={
                "better_side": side,
                "better_cvr": better.cvr,
                "better_conversions": better.conversions,
                "better_creatives": better.creatives_count,
                "worse_side": "discount_off" if side == "discount_on" else "discount_on",
                "worse_cvr": worse.cvr,
                "worse_conversions": worse.conversions,
                "worse_creatives": worse.creatives_count,
                "cvr_ratio": better.cvr / worse.cvr,
                "currency": better.currency,
            },
        )
    ]
