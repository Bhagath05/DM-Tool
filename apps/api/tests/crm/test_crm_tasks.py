"""Phase 6.5 Slice 3 — CRM tasks & calendar: recurrence math, link validation,
completion + next-occurrence, automation, cross-tenant. Hermetic — fake session,
no DB/network (audit stubbed)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.crm import automation
from aicmo.modules.crm import tasks_service as svc
from aicmo.modules.crm.models import Deal, Task
from aicmo.modules.crm.tasks_schemas import TaskCreate

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)


class _Session:
    def __init__(self, store=None):
        self._store = store or {}
        self.added: list = []

    async def get(self, _model, _id):
        return self._store.get(_id)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass

    async def delete(self, obj):
        pass


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(svc, "_audit", _noop)


def run(c):
    return asyncio.run(c)


# ---- recurrence math ----
def test_next_due_daily_weekly():
    base = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    assert svc.next_due(base, {"freq": "daily", "interval": 3}).day == 13
    assert svc.next_due(base, {"freq": "weekly", "interval": 2}).day == 24


def test_add_months_clamps_day():
    # Jan 31 + 1 month → Feb 28 (2026 is not a leap year)
    assert svc.add_months(datetime(2026, 1, 31, tzinfo=UTC), 1).date().isoformat() == "2026-02-28"
    # Dec + 2 months rolls the year
    assert svc.add_months(datetime(2026, 12, 15, tzinfo=UTC), 2).date().isoformat() == "2027-02-15"


# ---- stage_task defaults ----
def test_stage_task_defaults_owner_and_source():
    session = _Session()
    t = svc.stage_task(session, tenant=_TENANT, title="Call back", source="manual")
    assert t.owner_user_id == "rep-1" and t.assignee_user_id == "rep-1"
    assert t.created_by_user_id == "rep-1" and t.source == "manual"
    assert t in session.added


# ---- link validation ----
def test_create_task_rejects_cross_brand_deal():
    foreign = Deal(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(),
                   pipeline_id=uuid.uuid4(), title="X")
    session = _Session({foreign.id: foreign})
    with pytest.raises(HTTPException) as ei:
        run(svc.create_task(session, tenant=_TENANT,
                            payload=TaskCreate(title="t", deal_id=foreign.id)))
    assert ei.value.status_code == 404


def test_create_task_persists_recurrence_flag():
    session = _Session()
    payload = TaskCreate(title="Weekly sync", due_at=datetime(2026, 5, 1, tzinfo=UTC),
                         recurrence={"freq": "weekly", "interval": 1})
    out = run(svc.create_task(session, tenant=_TENANT, payload=payload))
    assert out.is_recurring is True and out.recurrence["freq"] == "weekly"


# ---- cross-tenant guard ----
def test_owned_task_cross_tenant_404():
    other = Task(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(), title="X")
    with pytest.raises(HTTPException) as ei:
        run(svc._owned_task(_Session({other.id: other}), tenant=_TENANT, task_id=other.id))
    assert ei.value.status_code == 404


# ---- completion ----
def test_complete_recurring_task_spawns_next_occurrence():
    task = Task(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, title="Weekly sync",
        activity_type="follow_up", status="open", priority="medium",
        due_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC), is_recurring=True,
        recurrence={"freq": "weekly", "interval": 1}, tags=[],
    )
    session = _Session({task.id: task})
    run(svc.complete_task(session, tenant=_TENANT, task_id=task.id))
    assert task.status == "completed" and task.completed_at is not None
    spawned = [o for o in session.added if isinstance(o, Task)]
    assert len(spawned) == 1
    assert spawned[0].due_at.date().isoformat() == "2026-05-08"  # +1 week
    assert spawned[0].recurrence_parent_id == task.id


def test_complete_meeting_task_drafts_followup():
    task = Task(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, title="Discovery call",
        activity_type="meeting", status="open", priority="medium", is_recurring=False,
        recurrence=None, due_at=None, tags=[], deal_id=None, contact_id=None,
        company_id=None, lead_id=None,
    )
    session = _Session({task.id: task})
    run(svc.complete_task(session, tenant=_TENANT, task_id=task.id))
    followups = [o for o in session.added if isinstance(o, Task) and o.source == "automation:meeting_completed"]
    assert len(followups) == 1
    assert "follow-up" in followups[0].title.lower()


# ---- automation ----
def test_on_deal_won_stages_grounded_task():
    deal = Deal(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND,
                pipeline_id=uuid.uuid4(), title="Acme renewal", company_id=None,
                primary_contact_id=None)
    session = _Session()
    automation.on_deal_won(session, tenant=_TENANT, deal=deal)
    staged = [o for o in session.added if isinstance(o, Task)]
    assert len(staged) == 1
    assert staged[0].source == "automation:deal_won"
    assert "Acme renewal" in staged[0].title  # grounded in the real deal
    assert staged[0].deal_id == deal.id
