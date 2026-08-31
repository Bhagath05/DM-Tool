"""Service glue over ConnectorMetric — with a fake session (no live DB)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from aicmo.modules.marketing_analytics import normalize, service

NOW = datetime.now(UTC)
BRAND = uuid.uuid4()


# --------------------------------------------------------------- fake session


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.captured = None

    async def execute(self, stmt):
        self.captured = stmt
        return _Result(self._rows)


def _row(provider, key, value, day_offset, period_end=None):
    return SimpleNamespace(
        provider_slug=provider,
        metric_key=key,
        metric_value=Decimal(str(value)),
        period_end=period_end,
        synced_at=NOW - timedelta(days=day_offset),
    )


def _daily(provider, key, value_fn, days=14):
    """One snapshot per day for `days` days; value_fn(day_offset) -> value."""
    return [_row(provider, key, value_fn(d), d) for d in range(days)]


# reach up (+40%), engagement flat (+2%) — the R1 dataset, 14 distinct days.
# Split at d < 7 so the boundary snapshot (day 7 ≈ now-7d) lands in the PREVIOUS
# window: current window (days 0-6) = high, previous window (days 7-13) = low.
def _reach_up_engagement_flat():
    rows = []
    rows += _daily("instagram_organic", "reach_28d", lambda d: 1400 if d < 7 else 1000)
    rows += _daily("instagram_organic", "engagement_rate", lambda d: 0.051 if d < 7 else 0.050)
    return rows


# --------------------------------------------------------------- empty state


@pytest.mark.asyncio
async def test_platforms_empty_when_no_rows():
    out = await service.get_platforms(_FakeSession([]), brand_id=BRAND)
    assert out.has_data is False
    assert out.platforms == [] and out.comparison == []
    assert out.sufficiency.level == "none"


@pytest.mark.asyncio
async def test_performance_report_empty_state_is_honest():
    out = await service.performance_report(_FakeSession([]), brand_id=BRAND)
    assert out.has_data is False
    assert out.headline == "Not enough data yet"
    assert out.whats_working == [] and out.whats_not_working == []


# --------------------------------------------------------------- platforms + comparison


@pytest.mark.asyncio
async def test_cross_platform_comparison_only_compares_valid_metrics():
    rows = []
    # audience is comparable across platforms
    rows += _daily("youtube", "subscribers", lambda d: 5000, days=10)
    rows += _daily("linkedin_organic", "followers", lambda d: 1000, days=10)
    # instagram reach — only one platform reports it → NOT a cross-platform row
    rows += _daily("instagram_organic", "reach_28d", lambda d: 2000, days=10)
    # youtube lifetime views — cumulative, NOT comparable across accounts
    rows += _daily("youtube", "views", lambda d: 999999, days=10)

    out = await service.get_platforms(_FakeSession(rows), brand_id=BRAND)
    assert out.has_data is True

    families = {row.metric for row in out.comparison}
    # audience IS compared (two platforms)
    assert normalize.AUDIENCE in families
    # reach is single-platform → excluded from comparison
    assert normalize.REACH not in families
    # lifetime views is never cross-compared
    assert normalize.LIFETIME_VIEWS not in families

    audience_row = next(r for r in out.comparison if r.metric == normalize.AUDIENCE)
    assert audience_row.leader_provider == "youtube"  # 5000 > 1000
    assert {e.provider_slug for e in audience_row.entries} == {"youtube", "linkedin_organic"}

    # lifetime views still SHOWN per-platform (just not compared) and marked non-comparable
    yt = next(p for p in out.platforms if p.provider_slug == "youtube")
    lv = next(m for m in yt.metrics if m.metric == normalize.LIFETIME_VIEWS)
    assert lv.comparable is False


@pytest.mark.asyncio
async def test_duplicate_snapshots_are_not_summed():
    # two snapshots the same day → representative latest, never 2000+2000
    rows = _daily("linkedin_organic", "followers", lambda d: 2000, days=10)
    rows.append(_row("linkedin_organic", "followers", 2000, 0))  # duplicate today
    out = await service.get_platforms(_FakeSession(rows), brand_id=BRAND)
    li = next(p for p in out.platforms if p.provider_slug == "linkedin_organic")
    metric = next(m for m in li.metrics if m.metric == normalize.AUDIENCE)
    assert metric.value == 2000  # not doubled


@pytest.mark.asyncio
async def test_unknown_metric_is_surfaced_but_not_comparable():
    rows = _daily("some_provider", "weird_new_metric", lambda d: 42, days=10)
    out = await service.get_platforms(_FakeSession(rows), brand_id=BRAND)
    assert out.has_data is True
    p = out.platforms[0]
    m = p.metrics[0]
    assert m.comparable is False
    assert out.comparison == []  # never compared


# --------------------------------------------------------------- trends


@pytest.mark.asyncio
async def test_trends_returns_bucketed_points():
    rows = _daily("instagram_organic", "reach_28d", lambda d: 1000 + (13 - d) * 10, days=14)
    out = await service.get_trends(_FakeSession(rows), brand_id=BRAND, granularity="day")
    assert out.has_data is True
    trend = out.trends[0]
    assert trend.metric == normalize.REACH
    assert len(trend.points) == 14  # one representative per day
    # newest point value is the largest (series grows toward today)
    assert trend.points[-1].value >= trend.points[0].value


@pytest.mark.asyncio
async def test_weekly_granularity_collapses_days():
    rows = _daily("instagram_organic", "reach_28d", lambda d: 1000, days=14)
    out = await service.get_trends(_FakeSession(rows), brand_id=BRAND, granularity="week")
    assert len(out.trends[0].points) < 14


# --------------------------------------------------------------- insights + report


@pytest.mark.asyncio
async def test_insights_service_fires_reach_up_engagement_flat():
    out = await service.get_insights(_FakeSession(_reach_up_engagement_flat()), brand_id=BRAND)
    assert out.has_data is True
    assert any(i.id.startswith("reach_up_engagement_flat") for i in out.insights)


@pytest.mark.asyncio
async def test_performance_report_splits_working_and_attention():
    rows = _reach_up_engagement_flat()
    # add a clear win: audience up 30%
    rows += _daily("youtube", "subscribers", lambda d: 1300 if d < 7 else 1000)
    out = await service.performance_report(_FakeSession(rows), brand_id=BRAND, narrate=False)
    assert out.has_data is True
    assert any(i.id.startswith("audience_growth") for i in out.whats_working)
    assert any(i.id.startswith("reach_up_engagement_flat") for i in out.whats_not_working)
    assert out.narrated is False  # deterministic path, no LLM


@pytest.mark.asyncio
async def test_short_history_yields_no_claims():
    rows = _daily("instagram_organic", "reach_28d", lambda d: 1000 + d, days=3)
    out = await service.get_insights(_FakeSession(rows), brand_id=BRAND)
    # data exists, but 3 days is not enough to claim a weekly trend
    assert out.has_data is True
    assert out.insights == []
    assert out.sufficiency.level == "short_term"


# --------------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_query_is_scoped_to_the_brand():
    session = _FakeSession(_daily("instagram_organic", "reach_28d", lambda d: 1000, days=10))
    await service.get_platforms(session, brand_id=BRAND)
    compiled = session.captured.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "brand_id" in sql  # scoping column present
    # the exact brand uuid is a bound parameter — no cross-tenant leak
    assert BRAND in compiled.params.values()
