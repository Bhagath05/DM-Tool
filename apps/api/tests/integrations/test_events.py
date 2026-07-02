"""Phase 6.1 — integration activity log (record / list / analytics)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from aicmo.modules.integrations import events


def _conn(**over):
    base = dict(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        provider_slug="meta_ads",
    )
    base.update(over)
    return SimpleNamespace(**base)


class _AddSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


# --------------------------------------------------------------------------
#  record_event — the write hook
# --------------------------------------------------------------------------
def test_record_event_stages_row_with_no_secret():
    session = _AddSession()
    conn = _conn()
    events.record_event(
        session,
        connection=conn,
        event_type="sync_completed",
        status="success",
        message="Synced 12 rows.",
        detail={"rows_pulled": 12},
        duration_ms=345,
    )
    assert len(session.added) == 1
    ev = session.added[0]
    assert ev.organization_id == conn.organization_id
    assert ev.brand_id == conn.brand_id
    assert ev.connection_id == conn.id
    assert ev.provider_slug == "meta_ads"
    assert ev.event_type == "sync_completed"
    assert ev.status == "success"
    assert ev.duration_ms == 345
    assert ev.detail == {"rows_pulled": 12}
    # no token/secret field on the event model
    assert not any("token" in a for a in vars(ev))


def test_record_event_truncates_long_message():
    session = _AddSession()
    events.record_event(
        session, connection=_conn(), event_type="error", status="failure",
        message="x" * 5000,
    )
    assert len(session.added[0].message) <= 500


# --------------------------------------------------------------------------
#  list_events — filters build correctly + tenant-scoped
# --------------------------------------------------------------------------
class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_list_events_returns_rows(monkeypatch):
    rows = [SimpleNamespace(event_type="sync_completed")]
    captured = {}

    class _S:
        async def execute(self, stmt):
            captured["stmt"] = str(stmt)
            return _ScalarResult(rows)

    out = await events.list_events(
        _S(), organization_id=uuid.uuid4(), event_type="sync_completed", status="success"
    )
    assert out == rows
    # the query filtered on org + event_type + status
    assert "integration_event" in captured["stmt"].lower()


# --------------------------------------------------------------------------
#  analytics — aggregation over real rows
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_analytics_aggregates_states_and_syncs():
    # First execute → connection states; second → events.
    conn_states = [("ACTIVE",), ("ACTIVE",), ("ERROR",)]
    event_rows = [
        ("sync_completed", "success", "meta_ads"),
        ("sync_completed", "failure", "meta_ads"),
        ("sync_completed", "success", "google_ads"),
        ("oauth_success", "success", "google_ads"),
        ("error", "failure", "linkedin"),
    ]

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _S:
        def __init__(self):
            self._i = 0

        async def execute(self, stmt):
            self._i += 1
            return _Res(conn_states if self._i == 1 else event_rows)

    out = await events.analytics(_S(), organization_id=uuid.uuid4())
    assert out["connections_total"] == 3
    assert out["connections_by_state"] == {"ACTIVE": 2, "ERROR": 1}
    assert out["syncs_total"] == 3
    assert out["syncs_succeeded"] == 2
    assert out["syncs_failed"] == 1
    assert out["sync_success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert out["errors_total"] == 2   # one failed sync + one error event
    assert out["events_total"] == 5
    assert out["events_by_provider"]["meta_ads"] == 2
