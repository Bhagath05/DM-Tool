"""Phase 7.5 — real-Postgres regression for the operations driver.

The daily autonomous cycle (`run_operations_cycle`, driven by
`operations_cycle_cron`) iterates active brands via `_active_brands`, which
imports the Brand model lazily. A wrong import module there raises ImportError
at RUNTIME ONLY — every unit test for the cron monkeypatches
`run_operations_cycle`, so the real `_active_brands` path had no coverage and a
broken import silently turned every daily cycle into a caught "failed" no-op.

This test exercises the REAL driver against Postgres with a seeded active brand,
so the import (and the end-to-end cycle) must genuinely work. It would have
caught the orgs-vs-brands Brand import bug.

Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_run_operations_cycle_scans_active_brands_for_real():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph
    from aicmo.modules.operations.driver import _active_brands, run_operations_cycle
    from aicmo.modules.operations.models import OperationsRun
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                               {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
            await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                               {"i": org, "s": f"o{tag}", "n": "O", "o": user})
            # status defaults to 'active'
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})

        # The real _active_brands import path (the regression guard).
        async with AsyncSession(eng, expire_on_commit=False) as s:
            actives = await _active_brands(s)
        assert any(b == brand for b, _ in actives), "seeded active brand must be scanned"

        # The whole cycle runs without raising and records an OperationsRun.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            result = await run_operations_cycle(s, trigger="test")
        assert result.status in ("completed", "partial")
        assert result.brands_scanned >= 1

        async with AsyncSession(eng, expire_on_commit=False) as s:
            runs = (await s.execute(
                select(OperationsRun).where(OperationsRun.trigger == "test")
            )).scalars().all()
            assert len(runs) >= 1
            assert runs[-1].status in ("completed", "partial")
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM operations_runs WHERE trigger='test'"))
            await conn.execute(text("DELETE FROM scheduled_work WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM operational_goals WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM operations_notifications WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM detected_events WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM metric_snapshots WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
