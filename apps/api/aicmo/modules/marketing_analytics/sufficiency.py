"""Data-sufficiency gating.

Every claim the Performance Marketer makes is gated on how much data actually
exists. This is the guardrail behind "never claim causation from insufficient
data": rules ask ``can_claim_trend`` / ``can_claim_comparison`` before firing,
and the API surfaces an honest empty/short-term state otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aicmo.modules.marketing_analytics.timeseries import Observation, distinct_days


class SufficiencyLevel(StrEnum):
    NONE = "none"  # nothing to say
    SINGLE_DAY = "single_day"  # one snapshot day — no trend at all
    SHORT_TERM = "short_term"  # a few days — short-term observation only
    WEEKLY = "weekly"  # >= 7 days — weekly trend analysis
    STRONG = "strong"  # >= 28 days — stronger comparisons


_MESSAGES: dict[SufficiencyLevel, str] = {
    SufficiencyLevel.NONE: "Not enough data yet.",
    SufficiencyLevel.SINGLE_DAY: "Only one day of data so far — too early to call a trend.",
    SufficiencyLevel.SHORT_TERM: "A few days of data — short-term observations only.",
    SufficiencyLevel.WEEKLY: "About a week of data — weekly trends are meaningful now.",
    SufficiencyLevel.STRONG: "Several weeks of data — trend comparisons are reliable.",
}


@dataclass(frozen=True)
class Sufficiency:
    level: SufficiencyLevel
    days_covered: int
    observations: int

    @property
    def message(self) -> str:
        return _MESSAGES[self.level]


def assess(observations: list[Observation]) -> Sufficiency:
    """Grade how much can be honestly claimed from these observations."""
    days = distinct_days(observations)
    count = len(observations)
    if count == 0:
        level = SufficiencyLevel.NONE
    elif days <= 1:
        level = SufficiencyLevel.SINGLE_DAY
    elif days < 7:
        level = SufficiencyLevel.SHORT_TERM
    elif days < 28:
        level = SufficiencyLevel.WEEKLY
    else:
        level = SufficiencyLevel.STRONG
    return Sufficiency(level=level, days_covered=days, observations=count)


_ORDER = {
    SufficiencyLevel.NONE: 0,
    SufficiencyLevel.SINGLE_DAY: 1,
    SufficiencyLevel.SHORT_TERM: 2,
    SufficiencyLevel.WEEKLY: 3,
    SufficiencyLevel.STRONG: 4,
}


def can_claim_trend(level: SufficiencyLevel) -> bool:
    """A directional trend claim needs at least a week of coverage."""
    return _ORDER[level] >= _ORDER[SufficiencyLevel.WEEKLY]


def can_claim_comparison(level: SufficiencyLevel, *, window_days: int) -> bool:
    """A period-over-period comparison needs coverage spanning both windows.

    A 7-day "this week vs last week" needs weekly+ data; a 30-day comparison
    needs the strong (multi-week) tier.
    """
    if window_days <= 7:
        return _ORDER[level] >= _ORDER[SufficiencyLevel.WEEKLY]
    return _ORDER[level] >= _ORDER[SufficiencyLevel.STRONG]
