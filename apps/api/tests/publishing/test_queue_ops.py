"""Phase 6.4 — enterprise publishing queue ops.

Covers the new lifecycle (cancel/pause/resume/reschedule), the approval gate
(submit → approve/reject/request-changes + the not-pending guard), and the
exponential-backoff schedule. Hermetic — a fake session, no DB, no network.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.publishing import queue_service

_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=uuid.uuid4(), brand_id=_BRAND, user_id="reviewer-1",
    user_uuid=uuid.uuid4(),
)


def _row(**over):
    now = datetime.now(UTC)
    base = dict(
        id=uuid.uuid4(), brand_id=_BRAND, content_asset_id=uuid.uuid4(),
        recommendation_id=None, platform="instagram", scheduled_at=now,
        publish_status="scheduled", platform_post_id=None, published_at=None,
        error_message=None, attempt_count=0, next_attempt_at=None,
        approval_status="not_required", approval_required=False,
        reviewed_by_user_id=None, approval_reason=None, schedule_timezone=None,
        created_at=now, updated_at=now,
    )
    base.update(over)
    return SimpleNamespace(**base)


class _Session:
    def __init__(self, row):
        self._row = row
        self.added: list = []

    async def get(self, _model, _id):
        return self._row

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


def run(coro):
    return asyncio.run(coro)


# ---- backoff ----
def test_backoff_is_exponential_and_capped():
    assert queue_service.backoff_seconds(0) == 0
    assert queue_service.backoff_seconds(1) == 300
    assert queue_service.backoff_seconds(2) == 600
    assert queue_service.backoff_seconds(3) == 1200
    assert queue_service.backoff_seconds(20) == 3600  # capped


def test_gate_constants_are_disjoint_and_complete():
    assert set(queue_service.PUBLISHABLE_APPROVALS).isdisjoint(queue_service.BLOCKED_APPROVALS)
    assert "approved" in queue_service.PUBLISHABLE_APPROVALS
    assert "pending" in queue_service.BLOCKED_APPROVALS


# ---- lifecycle ----
def test_cancel_sets_status_and_clears_backoff():
    row = _row(next_attempt_at=datetime.now(UTC))
    out = run(queue_service.cancel_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert out.publish_status == "cancelled"
    assert row.next_attempt_at is None


def test_cannot_cancel_published():
    row = _row(publish_status="published")
    with pytest.raises(HTTPException) as ei:
        run(queue_service.cancel_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert ei.value.status_code == 409


def test_pause_then_resume_roundtrip():
    row = _row()
    paused = run(queue_service.pause_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert paused.publish_status == "paused"
    resumed = run(queue_service.resume_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert resumed.publish_status == "scheduled"


def test_cannot_resume_non_paused():
    row = _row(publish_status="scheduled")
    with pytest.raises(HTTPException) as ei:
        run(queue_service.resume_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert ei.value.status_code == 409


def test_reschedule_resets_state():
    row = _row(publish_status="failed", error_message="boom", next_attempt_at=datetime.now(UTC))
    when = datetime.now(UTC) + timedelta(days=1)
    out = run(queue_service.reschedule_post(
        _Session(row), tenant=_TENANT, post_id=row.id, scheduled_at=when, schedule_timezone="Asia/Kolkata",
    ))
    assert out.publish_status == "scheduled"
    assert row.error_message is None
    assert row.next_attempt_at is None
    assert row.schedule_timezone == "Asia/Kolkata"


def test_cross_tenant_is_404():
    row = _row(brand_id=uuid.uuid4())  # different brand
    with pytest.raises(HTTPException) as ei:
        run(queue_service.cancel_post(_Session(row), tenant=_TENANT, post_id=row.id))
    assert ei.value.status_code == 404


# ---- approval gate ----
def test_submit_sets_pending_and_requires_approval():
    row = _row()
    out = run(queue_service.submit_for_approval(_Session(row), tenant=_TENANT, post_id=row.id))
    assert out.approval_status == "pending"
    assert row.approval_required is True


def test_approve_records_reviewer():
    row = _row(approval_status="pending", approval_required=True)
    out = run(queue_service.approve_post(
        _Session(row), tenant=_TENANT, post_id=row.id, reason="looks good",
    ))
    assert out.approval_status == "approved"
    assert row.reviewed_by_user_id == "reviewer-1"
    assert row.approval_reason == "looks good"


def test_reject_and_request_changes():
    for fn, expected in (
        (queue_service.reject_post, "rejected"),
        (queue_service.request_changes, "changes_requested"),
    ):
        row = _row(approval_status="pending", approval_required=True)
        out = run(fn(_Session(row), tenant=_TENANT, post_id=row.id, reason="no"))
        assert out.approval_status == expected


def test_cannot_decide_when_not_pending():
    row = _row(approval_status="not_required")
    with pytest.raises(HTTPException) as ei:
        run(queue_service.approve_post(
            _Session(row), tenant=_TENANT, post_id=row.id, reason=None,
        ))
    assert ei.value.status_code == 409
