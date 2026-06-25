"""Phase 1 — live billing: quota gate, webhook idempotency, flag gating.

PG-backed tests use the seeded plan/plan_quota tables (migration 0033) and
roll all writes back so the shared DB is untouched. Stripe is never called
(gateway functions are monkeypatched / the live path is flag-gated off).
"""

from __future__ import annotations

import socket
import uuid

import pytest

from aicmo.modules.billing import billing_live, plan_service


def _pg_up() -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("localhost", 5432))
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------
#  Pure / config
# ---------------------------------------------------------------------


def test_quota_status_unlimited_shape():
    st = billing_live.QuotaStatus(
        kind="generation", used=0, limit=None, remaining=None, over=False, near=False
    )
    assert st.limit is None and st.over is False


@pytest.mark.asyncio
async def test_enforce_quota_never_blocks_when_enforcement_off(monkeypatch):
    """With billing_enforce_limits off (default), enforce_quota must NEVER
    raise — even if the org were over limit. Fails open on any error."""
    from aicmo.config import get_settings

    monkeypatch.setenv("BILLING_ENFORCE_LIMITS", "false")
    get_settings.cache_clear()

    # A broken session would make check_quota raise → enforce must still
    # return (fail-open), not propagate.
    class _BrokenSession:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

        async def get(self, *a, **k):
            raise RuntimeError("db down")

    st = await billing_live.enforce_quota(
        _BrokenSession(), organization_id=uuid.uuid4(), kind="generation"
    )
    assert st.over is False  # fail-open
    get_settings.cache_clear()


# ---------------------------------------------------------------------
#  DB-backed quota (uses seeded plan_quota)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_service_reads_db_quotas():
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    eng = create_async_engine("postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo")
    plan_service.clear_cache()
    async with AsyncSession(eng) as s:
        # Seeded numbers from migration 0033.
        assert await plan_service.quota_for(s, "free", "generation") == 100
        assert await plan_service.quota_for(s, "starter", "campaign") == 100
        assert await plan_service.quota_for(s, "growth", "lead") == 5000
        # Early Access + Scale have NO quota rows → unlimited (None).
        assert await plan_service.quota_for(s, "early_access", "generation") is None
        assert await plan_service.quota_for(s, "scale", "lead") is None
    await eng.dispose()


@pytest.mark.asyncio
async def test_db_quota_change_takes_effect_without_code(monkeypatch):
    """The whole point of DB-configurable limits: change a number in
    plan_quota and the resolver reflects it (after cache clear)."""
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    eng = create_async_engine("postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo")
    try:
        async with AsyncSession(eng) as s:
            await s.execute(
                text(
                    "UPDATE plan_quota SET monthly_limit = 999 "
                    "WHERE plan_slug='free' AND usage_kind='generation'"
                )
            )
            plan_service.clear_cache()
            got = await plan_service.quota_for(s, "free", "generation")
            # never commit — roll back so the shared DB keeps its seed value
            await s.rollback()
        assert got == 999
    finally:
        plan_service.clear_cache()  # drop the dirty cached value
        await eng.dispose()


# ---------------------------------------------------------------------
#  Webhook idempotency (no Stripe — synthetic verified event)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_event_is_idempotent():
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    eng = create_async_engine("postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo")
    event_id = f"evt_test_{uuid.uuid4().hex}"
    event = {"id": event_id, "type": "customer.subscription.updated",
             "data": {"object": {"customer": "cus_nomatch"}}}
    try:
        async with AsyncSession(eng) as s:
            first = await billing_live.handle_stripe_event(s, event)
            await s.commit()
        async with AsyncSession(eng) as s:
            second = await billing_live.handle_stripe_event(s, event)
            await s.commit()
        assert first == "processed"
        assert second == "duplicate"  # re-delivery is a no-op
    finally:
        async with AsyncSession(eng) as s:
            await s.execute(
                text("DELETE FROM stripe_event WHERE event_id = :e"), {"e": event_id}
            )
            await s.commit()
        await eng.dispose()


@pytest.mark.asyncio
async def test_webhook_unhandled_type_is_acked_not_errored():
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    eng = create_async_engine("postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo")
    event_id = f"evt_test_{uuid.uuid4().hex}"
    event = {"id": event_id, "type": "ping.unknown", "data": {"object": {}}}
    try:
        async with AsyncSession(eng) as s:
            result = await billing_live.handle_stripe_event(s, event)
            await s.commit()
        # Unhandled types are recorded + acked (so Stripe stops retrying),
        # never raised.
        assert result == "ignored"
    finally:
        async with AsyncSession(eng) as s:
            await s.execute(
                text("DELETE FROM stripe_event WHERE event_id = :e"), {"e": event_id}
            )
            await s.commit()
        await eng.dispose()


# ---------------------------------------------------------------------
#  Checkout / portal flag gating (no Stripe)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_raises_billing_not_live_when_flag_off(monkeypatch):
    from aicmo.config import get_settings

    monkeypatch.setenv("BILLING_LIVE_ENABLED", "false")
    get_settings.cache_clear()

    class _S:  # never touched — flag check happens first
        pass

    with pytest.raises(billing_live.BillingNotLive):
        await billing_live.start_checkout(
            _S(), organization_id=uuid.uuid4(), plan_slug="growth",
            success_url="https://x", cancel_url="https://y",
        )
    get_settings.cache_clear()
