"""Shared grouping + aggregation helpers for the 9.1.5 intelligence layers.

Pure functions over `list[CreativeRollup]`. Every layer (audience /
creative / offer / scaling / dna) calls these to produce per-group
aggregates with the same min-sample discipline as 9.1.

Two invariants we never break:
  - Confidence is calibrated from sample size, not from margin alone.
  - Below-threshold groups are silenced, never approximated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from aicmo.modules.performance.schemas import CreativeRollup


# ---------------------------------------------------------------------
#  Thresholds — kept in lock-step with diagnostics.py / service.py
#  (group-level thresholds match per-creative thresholds; a "group" of
#  one creative degenerates to the per-creative case cleanly).
# ---------------------------------------------------------------------

MIN_GROUP_IMPRESSIONS = 500
MIN_GROUP_SPEND_MICROS = 1_000 * 1_000_000  # 1,000 of the row's currency
MIN_GROUP_CONVERSIONS = 1


# ---------------------------------------------------------------------
#  Aggregated group shape
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class GroupAggregate:
    """Roll-up of N CreativeRollups that share a grouping key.

    Carries the same metric surface as a single CreativeRollup so the
    diagnostic templates can speak about "this group" the way they
    already speak about "this creative."
    """

    key: object                       # the tag value (or tuple) we grouped by
    creative_refs: list[str]          # which creatives are in this group
    creatives_count: int
    impressions: int
    clicks: int
    conversions: int
    spend_micros: int
    conversion_value_micros: int
    currency: str
    # Common-mode tag snapshot so templates can name the group.
    audience: str | None
    concept_family: str | None
    emotion: str | None
    funnel_stage: str | None
    offer_type: str | None
    sample_state: str                 # 'sufficient' | 'insufficient'

    @property
    def spend(self) -> float:
        return self.spend_micros / 1_000_000

    @property
    def conversion_value(self) -> float:
        return self.conversion_value_micros / 1_000_000

    @property
    def cpl(self) -> float | None:
        return self.spend / self.conversions if self.conversions else None

    @property
    def cvr(self) -> float:
        return self.conversions / self.clicks if self.clicks else 0.0

    @property
    def roas(self) -> float | None:
        if self.spend == 0 or self.conversion_value == 0:
            return None
        return self.conversion_value / self.spend


# ---------------------------------------------------------------------
#  Grouping primitives
# ---------------------------------------------------------------------


KeyFn = Callable[[CreativeRollup], object | None]


def group_by(
    rollups: Iterable[CreativeRollup], key_fn: KeyFn
) -> dict[object, list[CreativeRollup]]:
    """Group rollups by an arbitrary key. Rollups whose key is None
    are skipped — NULL tags don't form a comparable group."""
    out: dict[object, list[CreativeRollup]] = defaultdict(list)
    for r in rollups:
        k = key_fn(r)
        if k is None:
            continue
        out[k].append(r)
    return out


def aggregate(key: object, members: list[CreativeRollup]) -> GroupAggregate:
    """Roll N CreativeRollups into a single GroupAggregate.

    Currency: take the most common across members; if mixed, the
    GroupAggregate carries the majority and the caller is responsible
    for the (rare) mixed-currency disclosure.
    """
    if not members:
        raise ValueError("aggregate(): empty member list")
    impressions = sum(m.impressions for m in members)
    clicks = sum(m.clicks for m in members)
    conversions = sum(m.conversions for m in members)
    spend_micros = sum(m.spend_micros for m in members)
    conv_value_micros = sum(m.conversion_value_micros for m in members)
    currencies = [m.currency for m in members]
    currency = max(set(currencies), key=currencies.count)

    sample_state = (
        "sufficient"
        if impressions >= MIN_GROUP_IMPRESSIONS
        and spend_micros >= MIN_GROUP_SPEND_MICROS
        and conversions >= MIN_GROUP_CONVERSIONS
        else "insufficient"
    )

    return GroupAggregate(
        key=key,
        creative_refs=[m.creative_ref for m in members],
        creatives_count=len(members),
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_micros=spend_micros,
        conversion_value_micros=conv_value_micros,
        currency=currency,
        audience=_common(members, lambda r: r.audience),
        concept_family=_common(members, lambda r: r.concept_family),
        emotion=_common(members, lambda r: r.emotion),
        funnel_stage=_common(members, lambda r: r.funnel_stage),
        offer_type=_common(members, lambda r: r.offer_type),
        sample_state=sample_state,
    )


def _common(members: list[CreativeRollup], pick: Callable) -> object | None:
    """Most-common value across members for a tag field. Returns None
    if all members are NULL on that field."""
    vals = [pick(m) for m in members if pick(m) is not None]
    if not vals:
        return None
    return max(set(vals), key=vals.count)


# ---------------------------------------------------------------------
#  Confidence calibration — group-level
# ---------------------------------------------------------------------


def group_confidence(
    winner: GroupAggregate,
    runner_up: GroupAggregate | None,
    *,
    base: int = 60,
    cap: int = 90,
    margin_metric: str = "cpl",
) -> int:
    """Calibrated confidence for a 'X wins over the field' diagnostic.

    Same shape as diagnostics._winner_confidence in 9.1 — kept separate
    so we can tune group-level rules without disturbing the per-creative
    rules pinned by Phase 9.1 tests.
    """
    score = base

    # Sample-size bonus (count winner's converted leads).
    if winner.conversions >= 50:
        score += 25
    elif winner.conversions >= 20:
        score += 15
    elif winner.conversions >= 5:
        score += 5

    # Margin bonus when we have a runner-up to compare against.
    if runner_up is not None:
        if margin_metric == "cpl" and winner.cpl and runner_up.cpl:
            if winner.cpl <= runner_up.cpl * 0.75:
                score += 10
        elif margin_metric == "cvr" and winner.cvr and runner_up.cvr:
            if winner.cvr >= runner_up.cvr * 1.5:
                score += 10
        elif margin_metric == "roas" and winner.roas and runner_up.roas:
            if winner.roas >= runner_up.roas * 1.5:
                score += 10

    return min(score, cap)


# ---------------------------------------------------------------------
#  Group filtering
# ---------------------------------------------------------------------


def keep_sufficient(groups: dict[object, GroupAggregate]) -> list[GroupAggregate]:
    """Subset to groups whose pooled sample crosses the threshold."""
    return [g for g in groups.values() if g.sample_state == "sufficient"]
