"""Pure time-series helpers over metric snapshots.

Every function here is DB-free so it can be unit-tested exhaustively. The input
is a list of :class:`Observation` (a value at a point in time); the output is
bucketed series and honest period-over-period comparisons.

Design constraint: the metrics we hold are stock/rolling/rate snapshots, never
per-event rows. So a "daily"/"weekly"/"monthly" value is the **representative
(latest) snapshot inside that bucket**, and a period comparison diffs the latest
snapshot of each window. We never *sum* snapshots — summing a trailing-28-day
reach across daily snapshots would multiply the same window many times over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

# |change%| below this reads as "flat" — noise, not a trend.
FLAT_BAND_PCT = 5.0
# |change%| at or above this is a "significant" move (used by the rule engine).
SIGNIFICANT_PCT = 15.0

Trend = Literal["up", "down", "flat", "insufficient"]


@dataclass(frozen=True)
class Observation:
    value: float
    observed_at: datetime


@dataclass(frozen=True)
class Bucket:
    """One aggregation bucket — its representative (latest) value."""

    bucket: date  # the bucket's start/anchor date
    value: float
    observed_at: datetime  # timestamp of the representative observation


@dataclass(frozen=True)
class Comparison:
    current: float | None
    previous: float | None
    absolute_change: float | None
    change_percent: float | None
    trend: Trend
    current_at: datetime | None = None
    previous_at: datetime | None = None
    window_days: int = 0


def _bucket_key(d: datetime, granularity: str) -> date:
    day = d.date()
    if granularity == "day":
        return day
    if granularity == "week":
        # ISO week → Monday of that week.
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    raise ValueError(f"unknown granularity: {granularity!r}")


def bucket_series(observations: list[Observation], *, granularity: str) -> list[Bucket]:
    """Collapse observations into representative buckets, oldest → newest.

    Within each bucket the **latest** observation wins (representative value),
    which is the honest choice for stock/rolling/rate snapshots. Buckets with no
    observation are simply absent — we do not invent zero-filled points that
    would fabricate a decline.
    """
    latest_in_bucket: dict[date, Observation] = {}
    for obs in observations:
        key = _bucket_key(obs.observed_at, granularity)
        cur = latest_in_bucket.get(key)
        if cur is None or obs.observed_at >= cur.observed_at:
            latest_in_bucket[key] = obs
    return [
        Bucket(
            bucket=key,
            value=latest_in_bucket[key].value,
            observed_at=latest_in_bucket[key].observed_at,
        )
        for key in sorted(latest_in_bucket)
    ]


def _latest_in_range(
    observations: list[Observation], *, start: datetime, end: datetime
) -> Observation | None:
    """Latest observation with start <= observed_at < end (None if none)."""
    best: Observation | None = None
    for obs in observations:
        if start <= obs.observed_at < end and (best is None or obs.observed_at >= best.observed_at):
            best = obs
    return best


def _round_pct(pct: float) -> float:
    return round(pct, 1)


def period_over_period(
    observations: list[Observation],
    *,
    window_days: int,
    now: datetime,
) -> Comparison:
    """Compare the current window's representative value with the prior window's.

    - current  = latest snapshot in ``[now - window, now]``
    - previous = latest snapshot in ``[now - 2*window, now - window)``

    ``change_percent`` is ``None`` when the previous value is missing or zero
    (division is undefined / misleading), but ``absolute_change`` is still
    reported. When either window has no snapshot, the trend is ``"insufficient"``
    and no change is claimed — we never fabricate a baseline.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    cur_start = now - timedelta(days=window_days)
    prev_start = now - timedelta(days=2 * window_days)

    current = _latest_in_range(observations, start=cur_start, end=now + timedelta(seconds=1))
    previous = _latest_in_range(observations, start=prev_start, end=cur_start)

    if current is None or previous is None:
        return Comparison(
            current=current.value if current else None,
            previous=previous.value if previous else None,
            absolute_change=None,
            change_percent=None,
            trend="insufficient",
            current_at=current.observed_at if current else None,
            previous_at=previous.observed_at if previous else None,
            window_days=window_days,
        )

    abs_change = current.value - previous.value
    if previous.value != 0:
        pct: float | None = _round_pct(abs_change / abs(previous.value) * 100.0)
    else:
        pct = None

    trend = _trend_from(abs_change=abs_change, pct=pct)
    return Comparison(
        current=current.value,
        previous=previous.value,
        absolute_change=abs_change,
        change_percent=pct,
        trend=trend,
        current_at=current.observed_at,
        previous_at=previous.observed_at,
        window_days=window_days,
    )


def _trend_from(*, abs_change: float, pct: float | None) -> Trend:
    if pct is not None:
        if abs(pct) < FLAT_BAND_PCT:
            return "flat"
        return "up" if pct > 0 else "down"
    # No percentage (previous was zero): any positive move is growth from nothing.
    if abs_change == 0:
        return "flat"
    return "up" if abs_change > 0 else "down"


def span_days(observations: list[Observation]) -> float:
    """Calendar span (in days) covered by the observations; 0 for <2 points."""
    if len(observations) < 2:
        return 0.0
    times = [o.observed_at for o in observations]
    return (max(times) - min(times)).total_seconds() / 86400.0


def distinct_days(observations: list[Observation]) -> int:
    """Number of distinct calendar days with at least one observation."""
    return len({o.observed_at.date() for o in observations})
