"""Phase 2 — automated metrics collection job (integrations/tasks.py).

Unit tests with mocks/fakes — no live provider credentials and no live DB.
Cover: no-op, collection, failure isolation, inactive skip, incremental
due-selection, tenant/audit scoping, token-safety, idempotent upsert.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from aicmo.modules.advisor.connectors import upsert_metric
from aicmo.modules.integrations import tasks

# --------------------------------------------------------------------- fakes


class _FakeSession:
    """Minimal async session: get() returns a preloaded conn; async ctx mgr."""

    def __init__(self, conns: dict | None = None, execute_result=None):
        self._conns = conns or {}
        self._execute_result = execute_result
        self.captured_stmt = None

    async def get(self, _model, cid):
        return self._conns.get(cid)

    async def execute(self, stmt):
        self.captured_stmt = stmt
        return self._execute_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


class _FakeLog:
    def __init__(self):
        self.calls: list = []

    def warning(self, *a, **k):
        self.calls.append(("warning", a, k))

    def info(self, *a, **k):
        self.calls.append(("info", a, k))


def _conn(state: str = "ACTIVE", provider: str = "youtube"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        state=state,
        provider_slug=provider,
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
    )


# ------------------------------------------------- collect_metrics_cron


@pytest.mark.asyncio
async def test_noop_when_none_due(monkeypatch):
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(tasks, "_due_connection_ids", AsyncMock(return_value=[]))
    sync = AsyncMock()
    monkeypatch.setattr(tasks.integrations_service, "sync", sync)

    out = await tasks.collect_metrics_cron({})

    assert out == {"due": 0, "synced": 0, "failed": 0}
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_collects_all_due(monkeypatch):
    a, b = _conn(), _conn()
    conns = {a.id: a, b.id: b}
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeSession(conns))
    monkeypatch.setattr(
        tasks, "_due_connection_ids", AsyncMock(return_value=[a.id, b.id])
    )
    sync = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(tasks.integrations_service, "sync", sync)

    out = await tasks.collect_metrics_cron({})

    assert out == {"due": 2, "synced": 2, "failed": 0}
    assert sync.await_count == 2


@pytest.mark.asyncio
async def test_failure_isolation_one_bad_account(monkeypatch):
    a, b, c = _conn(), _conn(), _conn()
    conns = {a.id: a, b.id: b, c.id: c}
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeSession(conns))
    monkeypatch.setattr(
        tasks, "_due_connection_ids", AsyncMock(return_value=[a.id, b.id, c.id])
    )

    async def _sync(_session, *, tenant, connection_id):
        if connection_id == b.id:
            raise RuntimeError("provider 500")
        return SimpleNamespace()

    monkeypatch.setattr(
        tasks.integrations_service, "sync", AsyncMock(side_effect=_sync)
    )

    out = await tasks.collect_metrics_cron({})

    # A and C still synced despite B failing — one account never aborts the run.
    assert out == {"due": 3, "synced": 2, "failed": 1}


@pytest.mark.asyncio
async def test_skips_connection_that_is_not_active(monkeypatch):
    a = _conn(state="ERROR")
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeSession({a.id: a}))
    monkeypatch.setattr(tasks, "_due_connection_ids", AsyncMock(return_value=[a.id]))
    sync = AsyncMock()
    monkeypatch.setattr(tasks.integrations_service, "sync", sync)

    out = await tasks.collect_metrics_cron({})

    sync.assert_not_awaited()  # never sync a non-ACTIVE connection
    assert out["synced"] == 0


@pytest.mark.asyncio
async def test_failure_never_logs_token_values(monkeypatch):
    a = _conn()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeSession({a.id: a}))
    monkeypatch.setattr(tasks, "_due_connection_ids", AsyncMock(return_value=[a.id]))
    secret = "ya29.SUPER-SECRET-ACCESS-TOKEN"
    monkeypatch.setattr(
        tasks.integrations_service,
        "sync",
        AsyncMock(side_effect=RuntimeError(f"auth failed: token was {secret}")),
    )
    fake_log = _FakeLog()
    monkeypatch.setattr(tasks, "log", fake_log)

    await tasks.collect_metrics_cron({})

    blob = repr(fake_log.calls)
    assert secret not in blob  # the token from the exception message is NOT logged
    assert "youtube" in blob  # provider slug is safe to log
    # the failure log carries the exception TYPE name, not str(exc)
    assert any(kw.get("error_type") == "RuntimeError" for _, _, kw in fake_log.calls)


# ------------------------------------------------- due-selection (incremental)


@pytest.mark.asyncio
async def test_due_selection_is_active_and_incremental():
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [])
    )
    session = _FakeSession(execute_result=result)

    await tasks._due_connection_ids(
        session, stale_before=datetime(2020, 1, 1, tzinfo=UTC)
    )

    sql = str(session.captured_stmt.compile(dialect=postgresql.dialect()))
    assert "state" in sql
    # never-synced OR stale → collected; fresh (last_sync_at >= stale_before) → skipped
    assert "last_sync_at IS NULL" in sql
    assert "last_sync_at <" in sql


# ------------------------------------------------- tenant scoping / audit skip


def test_system_tenant_skips_audit_and_scopes_to_connection():
    conn = _conn()
    ctx = tasks._system_tenant(conn)
    # user_uuid=None → service.sync skips the per-user audit write (FK-safe),
    # while org/brand scope preserves tenant isolation.
    assert ctx.user_uuid is None
    assert ctx.organization_id == conn.organization_id
    assert ctx.brand_id == conn.brand_id


# ------------------------------------------------- idempotency (reused upsert)


@pytest.mark.asyncio
async def test_upsert_metric_updates_existing_no_duplicate():
    existing = SimpleNamespace(metric_value=1.0, synced_at=None, raw_json={})
    result = SimpleNamespace(scalar_one_or_none=lambda: existing)
    added: list = []
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result), add=lambda row: added.append(row)
    )

    out = await upsert_metric(
        session,
        brand_id=uuid.uuid4(),
        provider_slug="youtube",
        metric_key="subscribers",
        metric_value=42.0,
        period_end=datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert out is existing
    assert existing.metric_value == 42.0  # updated in place
    assert added == []  # NO new row — re-run cannot duplicate


@pytest.mark.asyncio
async def test_upsert_metric_inserts_when_absent():
    result = SimpleNamespace(scalar_one_or_none=lambda: None)
    added: list = []
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result), add=lambda row: added.append(row)
    )

    out = await upsert_metric(
        session,
        brand_id=uuid.uuid4(),
        provider_slug="youtube",
        metric_key="views",
        metric_value=100.0,
    )

    assert len(added) == 1
    assert out.metric_value == 100.0
