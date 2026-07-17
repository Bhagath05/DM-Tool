"""Phase 4.4 — Work Scheduler tests (pure proposal rules + policy gating)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.autonomy.schemas import ActionPolicy, AutonomyPolicyConfig
from aicmo.modules.operations import scheduler


def _event(event_type, **over):
    base = dict(
        id=uuid.uuid4(), event_type=event_type, title="T", summary="S",
        status="new",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _goal(**over):
    base = dict(
        id=uuid.uuid4(), metric="leads", goal_type="increase", title="Grow leads",
        target_value=100.0, baseline_value=0.0, current_value=10.0,
        measurable=True, status="active",
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------
#  Pure proposal
# --------------------------------------------------------------------------
def test_events_map_to_work():
    drafts = scheduler.propose_from_events([
        _event("no_recent_leads"), _event("conversion_drop"), _event("publishing_failures"),
    ])
    kinds = {d.kind for d in drafts}
    assert {"content_generation", "campaign_update"} <= kinds
    # action types are set for policy evaluation
    assert all(d.action_type for d in drafts)
    # rationale cites the source event
    assert all("detected event" in d.rationale for d in drafts)


def test_unknown_event_produces_no_work():
    assert scheduler.propose_from_events([_event("some_unmapped_event")]) == []


def test_underprogressed_goal_schedules_work():
    behind = _goal(current_value=10, target_value=100)   # 10% → work
    ahead = _goal(current_value=80, target_value=100)    # 80% → no work
    drafts = scheduler.propose_from_goals([behind, ahead])
    assert len(drafts) == 1
    assert drafts[0].source_kind == "goal"


def test_unmeasurable_goal_no_work():
    g = _goal(measurable=False)
    assert scheduler.propose_from_goals([g]) == []


# --------------------------------------------------------------------------
#  schedule_work — policy gating + dedupe
# --------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """Serves schedule_work's queries in order: events, goals, weekly-report
    last-created, open dedupe keys. Weekly report is made NOT due (recent
    timestamp) so work counts reflect only event/goal proposals."""

    def __init__(self, events, goals, open_keys=()):
        from datetime import UTC, datetime

        self.added = []
        self._events = events
        self._goals = goals
        self._open = [(k,) for k in open_keys]
        self._recent = datetime.now(UTC)
        self._calls = 0

    async def execute(self, *a, **k):
        self._calls += 1
        if self._calls == 1:
            return _FakeResult(self._events)
        if self._calls == 2:
            return _FakeResult(self._goals)
        if self._calls == 3:
            return _FakeResult([], scalar=self._recent)  # weekly report NOT due
        return _FakeResult(self._open)

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_schedule_work_gates_everything_by_default(monkeypatch):
    # Default policy + master switch OFF → everything awaits approval.
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=AutonomyPolicyConfig()),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(autonomy_execution_enabled=False, operations_max_tasks_per_cycle=100),
    )
    session = _FakeSession(events=[_event("no_recent_leads")], goals=[])
    created = await scheduler.schedule_work(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4()
    )
    assert created >= 1
    work = session.added[0]
    assert work.requires_approval is True
    assert work.auto_eligible is False
    assert work.status == "awaiting_approval"


@pytest.mark.asyncio
async def test_schedule_work_auto_eligible_queues_when_policy_and_master_allow(monkeypatch):
    cfg = AutonomyPolicyConfig(
        policies={"content_generation": ActionPolicy(mode="auto_always")}
    )
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default", AsyncMock(return_value=cfg)
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(autonomy_execution_enabled=True, operations_max_tasks_per_cycle=100),
    )
    session = _FakeSession(events=[_event("no_recent_leads")], goals=[])
    await scheduler.schedule_work(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4()
    )
    work = session.added[0]
    assert work.auto_eligible is True
    assert work.status == "queued"  # released by policy, but still not executed here


@pytest.mark.asyncio
async def test_schedule_work_dedupes_against_open(monkeypatch):
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=AutonomyPolicyConfig()),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(autonomy_execution_enabled=False, operations_max_tasks_per_cycle=100),
    )
    ev = _event("no_recent_leads")
    brand = uuid.uuid4()
    dedupe = f"{brand}:content_generation:{ev.id}"
    session = _FakeSession(events=[ev], goals=[], open_keys=(dedupe,))
    created = await scheduler.schedule_work(
        session, organization_id=uuid.uuid4(), brand_id=brand
    )
    assert created == 0  # already open → not re-created
    assert session.added == []


# ---------------------------------------------------------------------
#  Phase 8 Priority 3 — max-tasks-per-cycle guardrail
# ---------------------------------------------------------------------


def _draft(priority: str, i: int):
    from aicmo.modules.operations.scheduler import WorkDraft

    return WorkDraft(
        kind=f"k{i}",
        action_type="ai_recommendation",
        title=f"Task {i}",
        description="",
        rationale="",
        priority=priority,
        source_kind="test",
        source_id=uuid.uuid4(),
    )


class _CapSession:
    """persist_drafts issues one query (_open_dedupe_keys) then session.add()s."""

    def __init__(self):
        self.added = []

    async def execute(self, *a, **k):
        return _FakeResult([])  # no open dedupe keys

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_max_tasks_cap_holds_back_extra_work_and_notifies(monkeypatch):
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=AutonomyPolicyConfig()),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(
            autonomy_execution_enabled=False, operations_max_tasks_per_cycle=3
        ),
    )
    # 5 drafts, cap = 3 → 3 work items + 1 "work_deferred" notification.
    drafts = [_draft("low", i) for i in range(5)]
    session = _CapSession()
    created = await scheduler.persist_drafts(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4(), drafts=drafts
    )
    assert created == 3, created
    kinds = [type(o).__name__ for o in session.added]
    # 3 ScheduledWork + 1 OperationsNotification (the "waiting for tomorrow" note).
    assert kinds.count("OperationsNotification") == 1, kinds
    assert kinds.count("ScheduledWork") == 3, kinds


@pytest.mark.asyncio
async def test_max_tasks_cap_keeps_highest_priority_first(monkeypatch):
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=AutonomyPolicyConfig()),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(
            autonomy_execution_enabled=False, operations_max_tasks_per_cycle=1
        ),
    )
    # A low then a high → the single surviving item must be the high one.
    drafts = [_draft("low", 0), _draft("high", 1)]
    session = _CapSession()
    created = await scheduler.persist_drafts(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4(), drafts=drafts
    )
    assert created == 1
    work = next(o for o in session.added if type(o).__name__ == "ScheduledWork")
    assert work.priority == "high", "cap must keep the most valuable work"


@pytest.mark.asyncio
async def test_under_cap_emits_no_deferral_note(monkeypatch):
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=AutonomyPolicyConfig()),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(
            autonomy_execution_enabled=False, operations_max_tasks_per_cycle=10
        ),
    )
    drafts = [_draft("medium", i) for i in range(2)]
    session = _CapSession()
    await scheduler.persist_drafts(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4(), drafts=drafts
    )
    kinds = [type(o).__name__ for o in session.added]
    assert "OperationsNotification" not in kinds, "no note when nothing was held back"
