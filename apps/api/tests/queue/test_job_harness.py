"""Phase 0 — ARQ tenant-context harness tests.

Layers:
  - pure unit (no DB): envelope round-trip, enqueue attaches envelope,
    kill-switch + no-pool no-ops.
  - live-DB (skip if PG down): the @tenant_job decorator opens a real
    session, sets the RLS GUC to the envelope's org, runs the body,
    commits, and clears contextvars on exit. Combined with tests/rls
    (which proves the GUC enforces isolation) this proves background
    jobs are tenant-isolated.
"""

from __future__ import annotations

import uuid

import pytest
import structlog
from sqlalchemy import text

from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TENANT_KW, TenantEnvelope, enqueue_tenant_job
from aicmo.tenancy.context import TenantContext


def _ctx() -> TenantContext:
    return TenantContext(
        user_id="clerk_abc",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner", "editor"}),
        permissions=frozenset({"content.create"}),
    )


# ---------------------------------------------------------------------
#  Envelope
# ---------------------------------------------------------------------


def test_envelope_round_trip():
    tenant = _ctx()
    env = TenantEnvelope.from_context(tenant)
    again = TenantEnvelope.from_payload(env.to_payload())
    assert again.organization_id == str(tenant.organization_id)
    assert again.user_uuid == str(tenant.user_uuid)
    assert again.brand_uuid() == tenant.brand_id
    assert again.role_slugs == sorted(tenant.role_slugs)


def test_envelope_handles_null_brand():
    tenant = TenantContext(
        user_id="u",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=None,
        member_id=uuid.uuid4(),
    )
    env = TenantEnvelope.from_context(tenant)
    assert env.brand_id is None
    assert env.brand_uuid() is None


# ---------------------------------------------------------------------
#  enqueue_tenant_job
# ---------------------------------------------------------------------


class _FakePool:
    def __init__(self):
        self.calls: list = []

    async def enqueue_job(self, function_name, *args, **kwargs):
        self.calls.append((function_name, args, kwargs))
        return "job-id"


@pytest.mark.asyncio
async def test_enqueue_attaches_envelope(monkeypatch):
    from aicmo.config import get_settings

    monkeypatch.setenv("JOBS_ENABLED", "true")
    get_settings.cache_clear()

    pool = _FakePool()
    job = await enqueue_tenant_job(pool, "some_job", 42, tenant=_ctx())
    assert job == "job-id"
    fn, args, kwargs = pool.calls[0]
    assert fn == "some_job"
    assert args == (42,)
    assert TENANT_KW in kwargs
    assert "organization_id" in kwargs[TENANT_KW]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_enqueue_noop_when_jobs_disabled(monkeypatch):
    from aicmo.config import get_settings

    monkeypatch.setenv("JOBS_ENABLED", "false")
    get_settings.cache_clear()

    pool = _FakePool()
    job = await enqueue_tenant_job(pool, "some_job", tenant=_ctx())
    assert job is None
    assert pool.calls == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_enqueue_noop_when_no_pool():
    job = await enqueue_tenant_job(None, "some_job", tenant=_ctx())
    assert job is None


# ---------------------------------------------------------------------
#  @tenant_job decorator
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decorator_raises_without_envelope():
    @tenant_job
    async def job(ctx, session, tenant):  # pragma: no cover - should raise first
        return "ran"

    with pytest.raises(RuntimeError, match="without a tenant envelope"):
        await job({})


def _pg_up() -> bool:
    import socket

    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("localhost", 5432))
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.asyncio
async def test_decorator_sets_rls_guc_to_envelope_org(monkeypatch):
    """With RLS flag on, the job session carries the envelope's org in
    the app.current_org_id GUC — the proof that jobs run tenant-scoped."""
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from aicmo.config import get_settings

    monkeypatch.setenv("DB_RLS_ENABLED", "true")
    get_settings.cache_clear()

    org = uuid.uuid4()
    payload = TenantEnvelope(
        user_uuid=str(uuid.uuid4()),
        organization_id=str(org),
        brand_id=None,
        role_slugs=["owner"],
    ).to_payload()

    @tenant_job
    async def probe(ctx, session, tenant):
        val = (
            await session.execute(
                text("SELECT current_setting('app.current_org_id', true)")
            )
        ).scalar_one()
        return val

    result = await probe({}, **{TENANT_KW: payload})
    assert result == str(org)
    # contextvars must be cleared after the job returns
    assert structlog.contextvars.get_contextvars() == {}
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_decorator_clears_context_on_error(monkeypatch):
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from aicmo.config import get_settings

    monkeypatch.setenv("DB_RLS_ENABLED", "false")
    get_settings.cache_clear()

    payload = TenantEnvelope(
        user_uuid=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        brand_id=None,
        role_slugs=[],
    ).to_payload()

    @tenant_job
    async def boom(ctx, session, tenant):
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await boom({}, **{TENANT_KW: payload})
    # even on error, no tenant tags leak to the next job
    assert structlog.contextvars.get_contextvars() == {}
    get_settings.cache_clear()
