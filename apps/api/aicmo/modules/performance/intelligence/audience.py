"""Audience Intelligence — Phase 9.1.5 layer 1.

Pure functions. Group the brand's per-creative rollups by the
`audience` tag and surface:

  - audience_winner   the audience tag with the cheapest CPL
  - audience_loser    an audience tag whose CPL is materially worse
                      than the winner's (≥ 1.5×)

We need at least TWO audiences with sufficient sample to fire — a
single audience can't be "the winner" relative to nothing.
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


def summarise_audiences(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    """Emit 0-2 audience drafts from the brand's rollup."""
    groups = group_by(rollups, key_fn=lambda r: r.audience)
    aggregates = {k: aggregate(k, members) for k, members in groups.items()}
    eligible = keep_sufficient(aggregates)
    if len(eligible) < 2:
        return []

    # Rank by CPL ascending. None-CPL groups are excluded — can't
    # compare on a metric we can't compute.
    ranked = sorted(
        [g for g in eligible if g.cpl is not None],
        key=lambda g: g.cpl,  # type: ignore[arg-type, return-value]
    )
    if len(ranked) < 2:
        return []

    winner = ranked[0]
    runner_up = ranked[1]
    worst = ranked[-1]

    drafts: list[DiagnosticDraft] = []

    # ---- Winner ----------------------------------------------------
    winner_conf = group_confidence(winner, runner_up=runner_up)
    if winner_conf >= 40:
        drafts.append(
            DiagnosticDraft(
                kind="audience_winner",
                impact_category=(
                    "revenue" if winner.conversion_value > 0 else "lead"
                ),
                confidence=winner_conf,
                subject_creative_ref=str(winner.key),
                evidence={
                    "audience": str(winner.key),
                    "creatives_count": winner.creatives_count,
                    "creative_refs": winner.creative_refs,
                    "impressions": winner.impressions,
                    "clicks": winner.clicks,
                    "conversions": winner.conversions,
                    "spend": winner.spend,
                    "currency": winner.currency,
                    "cpl": winner.cpl,
                    "roas": winner.roas,
                    "runner_up_audience": str(runner_up.key),
                    "runner_up_cpl": runner_up.cpl,
                    "field_size": len(ranked),
                },
            )
        )

    # ---- Loser -----------------------------------------------------
    # Only fire when there is a meaningful gap (≥ 1.5×) AND the worst
    # group is materially funded (otherwise it's a curiosity, not a
    # waste signal worth a card).
    if (
        worst.creative_refs != winner.creative_refs
        and worst.cpl is not None
        and winner.cpl is not None
        and worst.cpl >= winner.cpl * 1.5
        and worst.spend >= 500  # don't shout about tiny test spend
    ):
        # Confidence is one band below the winner — the loser is
        # derived from comparison, not from its own win.
        loser_conf = max(40, winner_conf - 10)
        drafts.append(
            DiagnosticDraft(
                kind="audience_loser",
                impact_category="cost",
                confidence=loser_conf,
                subject_creative_ref=str(worst.key),
                evidence={
                    "audience": str(worst.key),
                    "creatives_count": worst.creatives_count,
                    "creative_refs": worst.creative_refs,
                    "impressions": worst.impressions,
                    "conversions": worst.conversions,
                    "spend": worst.spend,
                    "currency": worst.currency,
                    "cpl": worst.cpl,
                    "winner_audience": str(winner.key),
                    "winner_cpl": winner.cpl,
                    "cpl_ratio": worst.cpl / winner.cpl,
                },
            )
        )

    return drafts
