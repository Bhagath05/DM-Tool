"""Settings → Security → Active Sessions now reads the first-party session
store (`user_sessions`). Verifies listing, current-session flagging, exclusion
of expired/revoked, per-session revoke, current-session refusal, and
revoke-all-others — against real Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aicmo.auth import sessions as auth_sessions
from aicmo.config import get_settings
from aicmo.modules.security import service
from tests._dbtest import async_dsn, pg_reachable

pytestmark = pytest.mark.asyncio


def _engine():
    return create_async_engine(async_dsn(), poolclass=None)


async def _new_user(s: AsyncSession):
    from aicmo.auth.password import hash_password
    from aicmo.modules.users.models import User

    u = User(
        email=f"sess-{uuid.uuid4().hex[:12]}@example.com",
        password_hash=hash_password("x-strong-password"),
        email_verified_at=datetime.now(UTC),
        status="active",
    )
    s.add(u)
    await s.flush()
    return u


async def test_active_sessions_reflect_first_party_store():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            _, cur = await auth_sessions.create_session(s, user_id=u.id, settings=settings)
            _, other = await auth_sessions.create_session(s, user_id=u.id, settings=settings)
            # An expired session must NOT appear as active.
            _, expired = await auth_sessions.create_session(s, user_id=u.id, settings=settings)
            expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await s.commit()

            listing = await service.list_sessions(s, user_id=u.id, current_session_id=str(cur.id))
            ids = {r.id for r in listing.sessions}
            assert cur.id in ids and other.id in ids
            assert expired.id not in ids  # expired excluded from active list
            current_rows = [r for r in listing.sessions if r.is_current]
            assert len(current_rows) == 1 and current_rows[0].id == cur.id
            # No token material is ever exposed by the read model.
            assert not any(hasattr(r, "token_hash") for r in listing.sessions)
    finally:
        await eng.dispose()


async def test_revoke_other_and_refuse_current():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raw_cur, cur = await auth_sessions.create_session(s, user_id=u.id, settings=settings)
            raw_other, other = await auth_sessions.create_session(
                s, user_id=u.id, settings=settings
            )
            await s.commit()

            # Revoking ANOTHER session works and kills it.
            await service.mark_session_revoked(
                s, user_id=u.id, session_row_id=other.id, current_session_id=str(cur.id)
            )
            await s.commit()
            assert await auth_sessions.resolve_session(s, raw_token=raw_other) is None
            # The current session survives.
            assert await auth_sessions.resolve_session(s, raw_token=raw_cur) is not None

            # Revoking the CURRENT session via this endpoint is refused (use sign-out).
            with pytest.raises(service.CurrentSessionRevokeRefused):
                await service.mark_session_revoked(
                    s, user_id=u.id, session_row_id=cur.id, current_session_id=str(cur.id)
                )

            # A session belonging to someone else is not found (no cross-user leak).
            with pytest.raises(service.SessionNotFound):
                await service.mark_session_revoked(
                    s, user_id=uuid.uuid4(), session_row_id=cur.id, current_session_id=None
                )
    finally:
        await eng.dispose()


async def test_revoke_all_others_keeps_current():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raw_cur, cur = await auth_sessions.create_session(s, user_id=u.id, settings=settings)
            raws = [
                (await auth_sessions.create_session(s, user_id=u.id, settings=settings))[0]
                for _ in range(3)
            ]
            await s.commit()

            resp = await service.revoke_all_sessions(
                s, user_id=u.id, current_session_id=str(cur.id)
            )
            await s.commit()
            assert resp.revoked_count == 3 and resp.skipped_current is True
            # Current alive; all others dead.
            assert await auth_sessions.resolve_session(s, raw_token=raw_cur) is not None
            for raw in raws:
                assert await auth_sessions.resolve_session(s, raw_token=raw) is None
    finally:
        await eng.dispose()
