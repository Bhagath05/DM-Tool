"""Time-series helpers — bucketing + honest period-over-period."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aicmo.modules.marketing_analytics.timeseries import (
    Observation,
    bucket_series,
    distinct_days,
    period_over_period,
    span_days,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _obs(day_offset: float, value: float) -> Observation:
    return Observation(value=value, observed_at=NOW - timedelta(days=day_offset))


# ---------------- bucketing ----------------


def test_daily_bucket_takes_latest_snapshot_not_sum():
    """Two snapshots on the same day collapse to the LATER one — never summed."""
    obs = [
        Observation(value=100, observed_at=datetime(2026, 8, 20, 6, tzinfo=UTC)),
        Observation(value=130, observed_at=datetime(2026, 8, 20, 18, tzinfo=UTC)),
    ]
    buckets = bucket_series(obs, granularity="day")
    assert len(buckets) == 1
    assert buckets[0].value == 130  # representative = latest, not 230


def test_weekly_bucket_anchors_to_monday():
    # 2026-08-21 is a Friday; its ISO week Monday is 2026-08-17.
    obs = [Observation(value=5, observed_at=datetime(2026, 8, 21, tzinfo=UTC))]
    buckets = bucket_series(obs, granularity="week")
    assert buckets[0].bucket == datetime(2026, 8, 17).date()


def test_monthly_bucket_anchors_to_first():
    obs = [Observation(value=5, observed_at=datetime(2026, 8, 21, tzinfo=UTC))]
    buckets = bucket_series(obs, granularity="month")
    assert buckets[0].bucket == datetime(2026, 8, 1).date()


def test_missing_days_are_omitted_not_zero_filled():
    """A gap must not fabricate a zero point (which would look like a crash)."""
    obs = [_obs(10, 100), _obs(3, 120)]  # nothing between
    buckets = bucket_series(obs, granularity="day")
    assert len(buckets) == 2
    assert all(b.value > 0 for b in buckets)


def test_buckets_sorted_oldest_to_newest():
    obs = [_obs(1, 3), _obs(9, 1), _obs(5, 2)]
    buckets = bucket_series(obs, granularity="day")
    assert [b.value for b in buckets] == [1, 2, 3]


# ---------------- period over period ----------------


def test_growth_percentage_and_absolute_change():
    obs = [_obs(9, 1000), _obs(0, 1230)]  # prev window vs current window
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.current == 1230
    assert c.previous == 1000
    assert c.absolute_change == 230
    assert c.change_percent == 23.0
    assert c.trend == "up"


def test_decline_is_reported_as_down():
    obs = [_obs(9, 1000), _obs(0, 700)]
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.change_percent == -30.0
    assert c.trend == "down"


def test_small_change_reads_as_flat():
    obs = [_obs(9, 1000), _obs(0, 1020)]
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.trend == "flat"  # +2% is inside the flat band


def test_insufficient_when_no_previous_window():
    obs = [_obs(1, 1000), _obs(0, 1100)]  # both in the current window
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.trend == "insufficient"
    assert c.change_percent is None
    assert c.absolute_change is None


def test_previous_zero_gives_no_percentage_but_keeps_absolute():
    obs = [_obs(9, 0), _obs(0, 50)]
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.change_percent is None  # division by zero would be misleading
    assert c.absolute_change == 50
    assert c.trend == "up"


def test_representative_uses_latest_snapshot_in_each_window():
    # current window has two snapshots; the later one is representative.
    obs = [_obs(9, 1000), _obs(2, 1100), _obs(0, 1200)]
    c = period_over_period(obs, window_days=7, now=NOW)
    assert c.current == 1200


def test_span_and_distinct_days():
    obs = [_obs(6, 1), _obs(6, 2), _obs(0, 3)]  # two calendar days
    assert distinct_days(obs) == 2
    assert round(span_days(obs)) == 6
