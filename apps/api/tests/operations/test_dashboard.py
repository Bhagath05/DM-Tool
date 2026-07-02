"""Phase 4.7 — Operations dashboard aggregation (mocked sub-reads)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.operations import service
from aicmo.modules.operations.schemas import (
    EventsView,
    MonitoringView,
    WorkList,
)


class _Result:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    async def execute(self, *a, **k):
        return _Result(scalar=None)  # no last operations run


_TENANT = SimpleNamespace(
    brand_id=uuid.uuid4(), organization_id=uuid.uuid4(), user_id="u1"
)


def _patch_common(monkeypatch, *, monitored, open_events, awaiting):
    monkeypatch.setattr(
        service, "monitoring_view",
        AsyncMock(return_value=MonitoringView(
            latest=None, history=[], monitored=monitored, note=None
        )),
    )
    monkeypatch.setattr(
        service, "events_view",
        AsyncMock(return_value=EventsView(items=[], open_count=open_events, note=None)),
    )
    monkeypatch.setattr(
        service, "work_view",
        AsyncMock(return_value=WorkList(items=[], awaiting_approval=awaiting)),
    )
    # sub-reads that are imported lazily inside dashboard() — patch their modules
    monkeypatch.setattr(
        "aicmo.modules.operations.goals.list_goals", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "aicmo.modules.learning.insights_service.list_insights",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=SimpleNamespace(
            autonomy_level="manual", execution_enabled=False, configured=False
        )),
    )
    monkeypatch.setattr(
        "aicmo.modules.orchestrator.service.build_plan",
        AsyncMock(return_value=SimpleNamespace(model_dump=lambda mode=None: {"summary": "x"})),
    )


@pytest.mark.asyncio
async def test_dashboard_headline_prioritises_approvals(monkeypatch):
    _patch_common(monkeypatch, monitored=True, open_events=3, awaiting=2)
    dash = await service.dashboard(_FakeSession(), tenant=_TENANT)
    assert dash.awaiting_approval_count == 2
    assert "need your approval" in dash.headline
    assert dash.autonomy.autonomy_level == "manual"
    assert dash.lifecycle == {"summary": "x"}


@pytest.mark.asyncio
async def test_dashboard_headline_when_unmonitored(monkeypatch):
    _patch_common(monkeypatch, monitored=False, open_events=0, awaiting=0)
    dash = await service.dashboard(_FakeSession(), tenant=_TENANT)
    assert "hasn't run yet" in dash.headline
    assert dash.system.monitored is False


@pytest.mark.asyncio
async def test_dashboard_headline_all_quiet(monkeypatch):
    _patch_common(monkeypatch, monitored=True, open_events=0, awaiting=0)
    dash = await service.dashboard(_FakeSession(), tenant=_TENANT)
    assert "All quiet" in dash.headline


@pytest.mark.asyncio
async def test_dashboard_survives_a_degraded_subread(monkeypatch):
    _patch_common(monkeypatch, monitored=True, open_events=1, awaiting=0)
    # Autonomy read blows up → dashboard still returns with safe defaults.
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    dash = await service.dashboard(_FakeSession(), tenant=_TENANT)
    assert dash.autonomy.autonomy_level == "manual"  # fell back safely
    assert dash.open_event_count == 1
