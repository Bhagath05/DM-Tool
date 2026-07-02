"""Phase 4.8 — Notification Center tests (emit for real changes, deduped)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from aicmo.modules.notifications.catalog import all_category_ids
from aicmo.modules.operations import notifier


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _FakeSession:
    """1st execute → existing dedupe keys; 2nd → achieved goals."""

    def __init__(self, existing_keys=(), achieved=()):
        self.added = []
        self._batches = [[(k,) for k in existing_keys], list(achieved)]
        self._i = 0

    async def execute(self, *a, **k):
        batch = self._batches[min(self._i, len(self._batches) - 1)]
        self._i += 1
        return _FakeResult(batch)

    def add(self, obj):
        self.added.append(obj)


def _event(severity="high"):
    return SimpleNamespace(
        id=uuid.uuid4(), severity=severity, title="Leads stopped", summary="0 leads",
    )


_ORG, _BRAND = uuid.uuid4(), uuid.uuid4()


@pytest.mark.asyncio
async def test_emits_for_high_event_and_approvals():
    session = _FakeSession()
    staged = await notifier.emit_for_cycle(
        session, organization_id=_ORG, brand_id=_BRAND,
        new_events=[_event("high")], work_created=3,
    )
    assert staged == 2  # event + approvals
    cats = {n.category for n in session.added}
    assert cats <= all_category_ids()  # only valid catalog categories used
    kinds = {n.kind for n in session.added}
    assert {"event", "approval"} == kinds


@pytest.mark.asyncio
async def test_low_severity_event_not_notified():
    session = _FakeSession()
    staged = await notifier.emit_for_cycle(
        session, organization_id=_ORG, brand_id=_BRAND,
        new_events=[_event("low")], work_created=0,
    )
    assert staged == 0
    assert session.added == []


@pytest.mark.asyncio
async def test_dedupes_against_existing():
    ev = _event("critical")
    session = _FakeSession(existing_keys=(f"event:{ev.id}",))
    staged = await notifier.emit_for_cycle(
        session, organization_id=_ORG, brand_id=_BRAND,
        new_events=[ev], work_created=0,
    )
    assert staged == 0  # already notified for this event


@pytest.mark.asyncio
async def test_goal_achievement_notifies_winner_alert():
    goal = SimpleNamespace(id=uuid.uuid4(), title="Reach 100 leads")
    session = _FakeSession(achieved=(goal,))
    staged = await notifier.emit_for_cycle(
        session, organization_id=_ORG, brand_id=_BRAND,
        new_events=[], work_created=0,
    )
    assert staged == 1
    assert session.added[0].category == "winner_alert"
    assert session.added[0].kind == "goal"
