"""Phase 4.1 — Operations Engine tests (no DB; mocked services)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from aicmo.modules.operations import driver, monitoring
from aicmo.modules.operations.router import _require_operations_secret


class _FakeResult:
    def scalars(self):
        return SimpleNamespace(all=lambda: [], first=lambda: None)

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, *a, **k):
        return _FakeResult()

    async def commit(self):
        pass

    async def flush(self):
        pass


_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()


# --------------------------------------------------------------------------
#  Monitoring — cadence idempotency
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_snapshot_skipped_within_cadence(monkeypatch):
    now = datetime.now(UTC)
    recent = SimpleNamespace(captured_at=now - timedelta(seconds=10), metrics={"total_leads": 5})
    monkeypatch.setattr(monitoring, "latest_snapshot", AsyncMock(return_value=recent))

    did, reason, _ = await monitoring.capture_brand_snapshot(
        _FakeSession(), organization_id=_ORG, brand_id=_BRAND, now=now
    )
    assert did is False and reason == "within_cadence"


@pytest.mark.asyncio
async def test_snapshot_captured_when_stale(monkeypatch):
    now = datetime.now(UTC)
    old = SimpleNamespace(captured_at=now - timedelta(seconds=9999), metrics={})
    monkeypatch.setattr(monitoring, "latest_snapshot", AsyncMock(return_value=old))
    monkeypatch.setattr(
        monitoring,
        "_gather_metrics",
        AsyncMock(return_value=({"total_leads": 12, "published_posts": 3}, ["analytics", "publishing"])),
    )
    session = _FakeSession()
    did, reason, metrics = await monitoring.capture_brand_snapshot(
        session, organization_id=_ORG, brand_id=_BRAND, now=now
    )
    assert did is True and reason == "captured"
    assert metrics["total_leads"] == 12
    assert len(session.added) == 1  # a MetricSnapshot was staged


@pytest.mark.asyncio
async def test_snapshot_not_written_when_all_sources_degraded(monkeypatch):
    monkeypatch.setattr(monitoring, "latest_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(monitoring, "_gather_metrics", AsyncMock(return_value=({}, [])))
    session = _FakeSession()
    did, reason, _ = await monitoring.capture_brand_snapshot(
        session, organization_id=_ORG, brand_id=_BRAND
    )
    assert did is False and reason == "sources_unavailable"
    assert session.added == []


# --------------------------------------------------------------------------
#  Driver — cycle + throttle
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cycle_throttled_when_recent_run(monkeypatch):
    now = datetime.now(UTC)
    recent_run = SimpleNamespace(started_at=now - timedelta(seconds=1))
    monkeypatch.setattr(driver, "_recent_run", AsyncMock(return_value=recent_run))

    out = await driver.run_operations_cycle(_FakeSession(), trigger="api", now=now)
    assert out.status == "throttled"
    assert out.snapshots_captured == 0


@pytest.mark.asyncio
async def test_cycle_scans_active_brands_and_counts(monkeypatch):
    monkeypatch.setattr(driver, "_recent_run", AsyncMock(return_value=None))
    monkeypatch.setattr(
        driver, "_active_brands", AsyncMock(return_value=[(_BRAND, _ORG), (uuid.uuid4(), _ORG)])
    )
    # First brand captures, second is within cadence.
    monkeypatch.setattr(
        driver.monitoring,
        "capture_brand_snapshot",
        AsyncMock(side_effect=[(True, "captured", {"a": 1}), (False, "within_cadence", {})]),
    )
    out = await driver.run_operations_cycle(_FakeSession(), trigger="api")
    assert out.brands_scanned == 2
    assert out.snapshots_captured == 1
    assert out.status == "completed"
    assert len(out.detail) == 2


@pytest.mark.asyncio
async def test_cycle_continues_past_a_failing_brand(monkeypatch):
    monkeypatch.setattr(driver, "_recent_run", AsyncMock(return_value=None))
    monkeypatch.setattr(
        driver, "_active_brands", AsyncMock(return_value=[(_BRAND, _ORG), (uuid.uuid4(), _ORG)])
    )
    monkeypatch.setattr(
        driver.monitoring,
        "capture_brand_snapshot",
        AsyncMock(side_effect=[RuntimeError("boom"), (True, "captured", {})]),
    )
    out = await driver.run_operations_cycle(_FakeSession(), trigger="api")
    assert out.brands_scanned == 2
    assert out.snapshots_captured == 1  # second brand still ran
    assert out.status == "partial"  # an error was recorded


# --------------------------------------------------------------------------
#  Tick security — the driver endpoint guard
# --------------------------------------------------------------------------
def _patch_secret(monkeypatch, value: str):
    # The router binds get_settings at import, so patch it on the router module.
    import aicmo.modules.operations.router as router_mod

    monkeypatch.setattr(
        router_mod, "get_settings", lambda: SimpleNamespace(operations_tick_secret=value)
    )


def test_tick_disabled_without_secret(monkeypatch):
    _patch_secret(monkeypatch, "")
    with pytest.raises(HTTPException) as ei:
        _require_operations_secret(x_operations_token=None)
    assert ei.value.status_code == 503


def test_tick_rejects_missing_or_wrong_token(monkeypatch):
    _patch_secret(monkeypatch, "s3cret")
    with pytest.raises(HTTPException) as ei:
        _require_operations_secret(x_operations_token=None)
    assert ei.value.status_code == 401
    with pytest.raises(HTTPException) as ei2:
        _require_operations_secret(x_operations_token="wrong")
    assert ei2.value.status_code == 401


def test_tick_accepts_correct_token(monkeypatch):
    _patch_secret(monkeypatch, "s3cret")
    assert _require_operations_secret(x_operations_token="s3cret") is None
