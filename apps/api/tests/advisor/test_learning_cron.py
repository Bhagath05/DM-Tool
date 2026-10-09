"""Phase 7.5 follow-up — the learning-loop scheduler (enqueue_learning_cycle_cron).

Verifies the daily cron that fans out one evaluate_advisor_outcomes per active
brand, WITHOUT a live Redis (a fake pool records enqueues) so it runs in the
normal suite. Real-worker end-to-end execution is proven separately against
isolated Redis + Postgres (see the Phase 7.5 report).

Covers: cron registration, correct per-brand scoped enqueueing, org/brand
isolation, inactive-brand exclusion, kill-switch (jobs_enabled) behavior, and
arq _job_id dedup of duplicate daily runs.
"""

from __future__ import annotations

import uuid

import pytest


class _FakePool:
    """Captures enqueue_job calls and simulates arq's _job_id dedup: a repeated
    _job_id (still 'in flight') returns None, exactly like ArqRedis.enqueue_job."""

    def __init__(self):
        self.calls: list[dict] = []
        self._seen: set[str] = set()

    async def enqueue_job(self, name, *args, _job_id=None, **kwargs):
        if _job_id is not None and _job_id in self._seen:
            return None  # arq dedup: a job with this id already exists
        if _job_id is not None:
            self._seen.add(_job_id)
        self.calls.append({"name": name, "job_id": _job_id, "tenant": kwargs.get("_tenant")})
        return object()  # a truthy "Job"


def test_learning_cron_is_registered_on_the_worker():
    from aicmo.modules.advisor.tasks import enqueue_learning_cycle_cron
    from aicmo.queue.worker import CRON_JOBS

    registered = {getattr(c, "coroutine", None) for c in CRON_JOBS}
    assert enqueue_learning_cycle_cron in registered


@pytest.mark.asyncio
async def test_enqueues_one_scoped_job_per_active_brand():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.advisor.tasks import enqueue_learning_cycle_cron
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    # Two orgs, each with an active brand, plus one INACTIVE brand (must be skipped).
    o1, b1, u1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    o2, b2, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    b_inactive = uuid.uuid4()
    try:
        async with eng.begin() as conn:
            for o, b, u, t in ((o1, b1, u1, f"{tag}a"), (o2, b2, u2, f"{tag}b")):
                await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                                   {"i": u, "c": f"c{t}", "e": f"{t}@t.local"})
                await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                                   {"i": o, "s": f"o{t}", "n": "O", "o": u})
                await conn.execute(
                    text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                    {"i": b, "o": o, "s": f"b{t}", "n": "B", "u": u})
            # inactive brand under org1 — scheduler must not enqueue it
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id, status) "
                     "VALUES (:i,:o,:s,:n,:u,'archived')"),
                {"i": b_inactive, "o": o1, "s": f"bz{tag}", "n": "Z", "u": u1})

        pool = _FakePool()
        res = await enqueue_learning_cycle_cron({"redis": pool})

        # Only the two ACTIVE brands were enqueued, each scoped to its own tenant.
        ours = [c for c in pool.calls if c["tenant"] and uuid.UUID(c["tenant"]["brand_id"]) in {b1, b2}]
        assert res["status"] == "ok"
        assert len(ours) == 2
        by_brand = {c["tenant"]["brand_id"]: c for c in ours}
        # org/owner are server-derived from the DB (never from input) and correct.
        assert by_brand[str(b1)]["tenant"]["organization_id"] == str(o1)
        assert by_brand[str(b1)]["tenant"]["user_uuid"] == str(u1)
        assert by_brand[str(b2)]["tenant"]["organization_id"] == str(o2)
        # all target the existing registered learning job, with a per-brand daily id
        assert all(c["name"] == "evaluate_advisor_outcomes" for c in ours)
        assert all(c["job_id"].startswith(f"learning:{c['tenant']['brand_id']}:") for c in ours)
        # the inactive brand was excluded
        assert not any(c["tenant"]["brand_id"] == str(b_inactive) for c in ours)
    finally:
        async with eng.begin() as conn:
            for o, u in ((o1, u1), (o2, u2)):
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
        await eng.dispose()


@pytest.mark.asyncio
async def test_duplicate_daily_run_is_deduped():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.advisor.tasks import enqueue_learning_cycle_cron
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    o, b, u = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                               {"i": u, "c": f"c{tag}", "e": f"{tag}@t.local"})
            await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                               {"i": o, "s": f"o{tag}", "n": "O", "o": u})
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": b, "o": o, "s": f"b{tag}", "n": "B", "u": u})

        pool = _FakePool()  # same pool → same _job_id set → arq-style dedup
        first = await enqueue_learning_cycle_cron({"redis": pool})
        second = await enqueue_learning_cycle_cron({"redis": pool})
        mine = [c for c in pool.calls if c["tenant"] and c["tenant"]["brand_id"] == str(b)]
        assert first["status"] == "ok" and second["status"] == "ok"
        # The brand is enqueued once; the duplicate same-day run adds nothing.
        assert len(mine) == 1
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": o})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": o})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
        await eng.dispose()


@pytest.mark.asyncio
async def test_kill_switch_disables_scheduling():
    import os

    from aicmo.config import get_settings
    from aicmo.modules.advisor.tasks import enqueue_learning_cycle_cron

    pool = _FakePool()
    get_settings.cache_clear()
    os.environ["JOBS_ENABLED"] = "false"
    try:
        res = await enqueue_learning_cycle_cron({"redis": pool})
    finally:
        os.environ.pop("JOBS_ENABLED", None)
        get_settings.cache_clear()
    assert res["status"] == "disabled"
    assert pool.calls == []
