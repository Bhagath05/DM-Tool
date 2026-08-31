"""Data-sufficiency gating."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aicmo.modules.marketing_analytics.sufficiency import (
    SufficiencyLevel,
    assess,
    can_claim_comparison,
    can_claim_trend,
)
from aicmo.modules.marketing_analytics.timeseries import Observation

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _days(n: int) -> list[Observation]:
    return [Observation(value=float(i), observed_at=NOW - timedelta(days=i)) for i in range(n)]


def test_no_data_is_none_level():
    s = assess([])
    assert s.level == SufficiencyLevel.NONE
    assert s.observations == 0
    assert "Not enough data" in s.message


def test_single_day_blocks_trend_claims():
    obs = [
        Observation(value=1, observed_at=NOW),
        Observation(value=2, observed_at=NOW - timedelta(hours=6)),
    ]
    s = assess(obs)
    assert s.level == SufficiencyLevel.SINGLE_DAY
    assert can_claim_trend(s.level) is False


def test_short_term_a_few_days():
    s = assess(_days(3))
    assert s.level == SufficiencyLevel.SHORT_TERM
    assert can_claim_trend(s.level) is False


def test_weekly_enables_trend_and_7d_comparison():
    s = assess(_days(10))
    assert s.level == SufficiencyLevel.WEEKLY
    assert can_claim_trend(s.level) is True
    assert can_claim_comparison(s.level, window_days=7) is True
    # a 30-day comparison still needs the strong tier
    assert can_claim_comparison(s.level, window_days=30) is False


def test_strong_enables_long_comparisons():
    s = assess(_days(35))
    assert s.level == SufficiencyLevel.STRONG
    assert can_claim_comparison(s.level, window_days=30) is True
