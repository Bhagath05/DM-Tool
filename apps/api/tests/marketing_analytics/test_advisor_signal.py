"""Phase 4 — advisor analytics signal generation (read-only, tenant-scoped)."""

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


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Routes the ConnectorMetric read vs the connection-presence read by the
    table named in the compiled statement."""

    def __init__(self, metric_rows=None, conn_rows=None):
        self._metric_rows = metric_rows or []
        self._conn_rows = conn_rows or []
        self.captured_metric = None
        self.captured_conn = None

    async def execute(self, stmt):
        # Phase 5: advisor_signal also reads the per-content store. Route those
        # (check them before integration_connection, whose column name appears in
        # the social_assets SELECT) to empty so this test isolates the metric read.
        s = str(stmt)
        if "social_assets" in s or "performance_signals" in s:
            return _Result([])
        if "integration_connection" in s:
            self.captured_conn = stmt
            return _Result(self._conn_rows)
        self.captured_metric = stmt
        return _Result(self._metric_rows)


def _row(provider, key, value, day_offset, period_end=None):
    return SimpleNamespace(
        provider_slug=provider,
        metric_key=key,
        metric_value=Decimal(str(value)),
        period_end=period_end,
        synced_at=NOW - timedelta(days=day_offset),
    )


def _daily(provider, key, value_fn, days=14):
    return [_row(provider, key, value_fn(d), d) for d in range(days)]


def _conn():
    return [SimpleNamespace(id=uuid.uuid4())]


# reach +40%, engagement flat — 14 distinct days (weekly tier).
def _reach_up_engagement_flat():
    rows = _daily("instagram_organic", "reach_28d", lambda d: 1400 if d < 7 else 1000)
    rows += _daily("instagram_organic", "engagement_rate", lambda d: 0.051 if d < 7 else 0.050)
    return rows


# ---------------- empty states ----------------


@pytest.mark.asyncio
async def test_signal_empty_no_connection():
    sig = await service.advisor_signal(_FakeSession(), brand_id=BRAND)
    assert sig.has_data is False
    assert sig.connected is False
    assert sig.empty_reason == "no_connection"
    assert "Connect a marketing account" in sig.empty_message


@pytest.mark.asyncio
async def test_signal_connected_but_no_metrics():
    sig = await service.advisor_signal(_FakeSession(conn_rows=_conn()), brand_id=BRAND)
    assert sig.has_data is False
    assert sig.connected is True
    assert sig.empty_reason == "no_metrics"


@pytest.mark.asyncio
async def test_signal_short_history_reports_no_trend():
    rows = _daily("instagram_organic", "reach_28d", lambda d: 1000 + d, days=3)
    sig = await service.advisor_signal(_FakeSession(rows, _conn()), brand_id=BRAND)
    assert sig.has_data is True
    assert sig.empty_reason == "short_history"
    assert sig.insights == []  # not enough history to claim a weekly trend
    # any evidence present must NOT assert a change (comparison is insufficient)
    assert all(e.change_percent is None for e in sig.evidence)


# ---------------- weekly evidence ----------------


@pytest.mark.asyncio
async def test_signal_weekly_evidence_is_computed():
    sig = await service.advisor_signal(
        _FakeSession(_reach_up_engagement_flat(), _conn()), brand_id=BRAND
    )
    assert sig.has_data is True
    assert sig.data_sufficiency == "weekly"
    assert sig.empty_reason is None
    # a reach-up/engagement-flat insight fired
    assert any(i.id.startswith("reach_up_engagement_flat") for i in sig.insights)
    # reach evidence exists and reflects the computed +40%
    reach_ev = [e for e in sig.evidence if e.metric == normalize.REACH]
    assert reach_ev and reach_ev[0].change_percent == 40.0
    assert sig.confidence_band in ("medium", "low")


@pytest.mark.asyncio
async def test_signal_multi_platform_evidence():
    rows = _reach_up_engagement_flat()
    rows += _daily("youtube", "subscribers", lambda d: 1300 if d < 7 else 1000)
    rows += _daily("linkedin_organic", "followers", lambda d: 500, days=14)
    sig = await service.advisor_signal(_FakeSession(rows, _conn()), brand_id=BRAND)
    platforms = {p.provider_slug for p in sig.platforms}
    assert {"instagram_organic", "youtube", "linkedin_organic"} <= platforms


# ---------------- evidence integrity ----------------


@pytest.mark.asyncio
async def test_signal_evidence_only_references_real_platform_metrics():
    sig = await service.advisor_signal(
        _FakeSession(_reach_up_engagement_flat(), _conn()), brand_id=BRAND
    )
    present = {(p.provider_slug, m.metric) for p in sig.platforms for m in p.metrics}
    for e in sig.evidence:
        assert (e.provider, e.metric) in present  # never a fabricated metric
    # every insight's evidence is also grounded in the platform metrics
    for insight in sig.insights:
        for e in insight.evidence:
            assert (e.provider, e.metric) in present


# ---------------- tenant isolation ----------------


@pytest.mark.asyncio
async def test_signal_queries_are_scoped_to_the_brand():
    session = _FakeSession(_reach_up_engagement_flat(), _conn())
    await service.advisor_signal(session, brand_id=BRAND)
    metric_sql = session.captured_metric.compile(dialect=postgresql.dialect())
    assert "brand_id" in str(metric_sql)
    assert BRAND in metric_sql.params.values()


@pytest.mark.asyncio
async def test_signal_connection_check_scoped_to_brand():
    session = _FakeSession(conn_rows=[])  # triggers the connection lookup
    await service.advisor_signal(session, brand_id=BRAND)
    conn_sql = session.captured_conn.compile(dialect=postgresql.dialect())
    assert "brand_id" in str(conn_sql)
    assert BRAND in conn_sql.params.values()
