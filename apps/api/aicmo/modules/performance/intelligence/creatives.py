"""Creative Intelligence — Phase 9.1.5 layer 2.

Pure functions. Group the rollup cube along each creative-side tag
and surface the best-performing slice. Plus `summarise_patterns` for
the (concept_family × emotion) combo we use as a "hook proxy" per
the approved plan, and `summarise_creative_dna` for the apex
(audience × emotion × concept × offer × funnel_stage) combo card.

DNA requires ALL FIVE tags to be present — without them, the pattern
isn't reusable. We never fire DNA on a partial fingerprint.
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


# ---------------------------------------------------------------------
#  Tag-level winners
# ---------------------------------------------------------------------


def summarise_concepts(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    return _tag_winner(
        rollups,
        kind="concept_winner",
        key_fn=lambda r: r.concept_family,
        tag_name="concept_family",
    )


def summarise_emotions(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    return _tag_winner(
        rollups,
        kind="emotion_winner",
        key_fn=lambda r: r.emotion,
        tag_name="emotion",
    )


def summarise_funnel_stages(
    rollups: list[CreativeRollup],
) -> list[DiagnosticDraft]:
    return _tag_winner(
        rollups,
        kind="funnel_winner",
        key_fn=lambda r: r.funnel_stage,
        tag_name="funnel_stage",
    )


# ---------------------------------------------------------------------
#  Combo signals
# ---------------------------------------------------------------------


def summarise_patterns(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    """Best (concept_family × emotion) combo — the "hook proxy" card.

    Same shape as the tag winners but keyed on a 2-tuple. Confidence
    is capped one band lower (85) because combo signals are noisier.
    """
    drafts = _tag_winner(
        rollups,
        kind="pattern_winner",
        key_fn=lambda r: (
            (r.concept_family, r.emotion)
            if r.concept_family and r.emotion
            else None
        ),
        tag_name="pattern",
        confidence_cap=85,
    )
    # Annotate evidence so the recommender can render "concept × emotion".
    for d in drafts:
        key = d.evidence.get("pattern")
        if isinstance(key, tuple) and len(key) == 2:
            d.evidence["concept_family"] = key[0]
            d.evidence["emotion"] = key[1]
            d.evidence["pattern_label"] = f"{key[0]} × {key[1]}"
    return drafts


def summarise_creative_dna(
    rollups: list[CreativeRollup],
) -> list[DiagnosticDraft]:
    """The apex card — best (audience × emotion × concept × offer ×
    funnel_stage) combination.

    Fires AT MOST ONE draft. Requires ALL FIVE tags non-NULL on every
    member of the winning combo. Otherwise we'd be claiming a
    "reusable pattern" that's structurally incomplete.

    Confidence capped at 80 because:
      - The combo is the most derived signal we emit.
      - It will often have the smallest sample of any group.
    """
    def key_fn(r: CreativeRollup) -> object | None:
        if not all([r.audience, r.concept_family, r.emotion, r.offer_type, r.funnel_stage]):
            return None
        return (r.audience, r.concept_family, r.emotion, r.offer_type, r.funnel_stage)

    groups = group_by(rollups, key_fn=key_fn)
    aggregates = {k: aggregate(k, members) for k, members in groups.items()}
    eligible = keep_sufficient(aggregates)
    if not eligible:
        return []

    # Rank by CPL (with ROAS as tiebreak when both have value).
    ranked = sorted(
        [g for g in eligible if g.cpl is not None],
        key=lambda g: (g.cpl, -(g.roas or 0)),  # type: ignore[arg-type]
    )
    if not ranked:
        return []

    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    conf = group_confidence(winner, runner_up=runner_up, cap=80)
    if conf < 40:
        return []

    audience, concept, emotion, offer, funnel = winner.key  # type: ignore[misc]
    return [
        DiagnosticDraft(
            kind="creative_dna",
            impact_category=(
                "revenue" if winner.conversion_value > 0 else "lead"
            ),
            confidence=conf,
            subject_creative_ref=f"dna:{audience}|{concept}|{emotion}|{offer}|{funnel}",
            evidence={
                "audience": audience,
                "concept_family": concept,
                "emotion": emotion,
                "offer_type": offer,
                "funnel_stage": funnel,
                "creatives_count": winner.creatives_count,
                "creative_refs": winner.creative_refs,
                "impressions": winner.impressions,
                "clicks": winner.clicks,
                "conversions": winner.conversions,
                "spend": winner.spend,
                "currency": winner.currency,
                "cpl": winner.cpl,
                "roas": winner.roas,
                "runner_up_cpl": runner_up.cpl if runner_up else None,
                "field_size": len(ranked),
            },
        )
    ]


# ---------------------------------------------------------------------
#  Internal helper — the shared "tag winner" body
# ---------------------------------------------------------------------


def _tag_winner(
    rollups: list[CreativeRollup],
    *,
    kind: str,
    key_fn,
    tag_name: str,
    confidence_cap: int = 90,
) -> list[DiagnosticDraft]:
    groups = group_by(rollups, key_fn=key_fn)
    aggregates = {k: aggregate(k, members) for k, members in groups.items()}
    eligible = keep_sufficient(aggregates)
    # Need at least 2 to call one a "winner" with comparative meaning.
    ranked = sorted(
        [g for g in eligible if g.cpl is not None],
        key=lambda g: g.cpl,  # type: ignore[arg-type, return-value]
    )
    if len(ranked) < 2:
        return []

    winner = ranked[0]
    runner_up = ranked[1]
    conf = group_confidence(winner, runner_up=runner_up, cap=confidence_cap)
    if conf < 40:
        return []

    return [
        DiagnosticDraft(
            kind=kind,  # type: ignore[arg-type]
            impact_category=(
                "revenue" if winner.conversion_value > 0 else "lead"
            ),
            confidence=conf,
            subject_creative_ref=str(winner.key),
            evidence={
                tag_name: winner.key,
                "creatives_count": winner.creatives_count,
                "creative_refs": winner.creative_refs,
                "impressions": winner.impressions,
                "clicks": winner.clicks,
                "conversions": winner.conversions,
                "spend": winner.spend,
                "currency": winner.currency,
                "cpl": winner.cpl,
                "roas": winner.roas,
                "runner_up": str(runner_up.key),
                "runner_up_cpl": runner_up.cpl,
                "field_size": len(ranked),
            },
        )
    ]
