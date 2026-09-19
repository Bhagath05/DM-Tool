"""First-party auth — security core + account lifecycle (real Postgres).

Exercises the primitives (Argon2id, opaque tokens) and the service/store layer
(sessions, single-use email tokens, throttling, signup→verify→signin→reset→
change) against a live database. Skips cleanly when Postgres is unreachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aicmo.auth import email_tokens, service, sessions
from aicmo.auth.email import set_email_sender
from aicmo.auth.password import hash_password, needs_rehash, verify_password
from aicmo.auth.tokens import constant_time_equals, generate_token, hash_token
from aicmo.config import get_settings
from aicmo.modules.users.models import User
from tests._dbtest import async_dsn, pg_reachable

pytestmark = pytest.mark.asyncio


def _engine():
    return create_async_engine(async_dsn(), poolclass=None)


def _tag() -> str:
    return uuid.uuid4().hex[:12]


class _CaptureSender:
    """Grabs the emailed links so tests can extract the raw one-time token."""

    def __init__(self) -> None:
        self.verify: list[tuple[str, str]] = []
        self.reset: list[tuple[str, str]] = []

    async def send_verification(self, *, to: str, link: str) -> None:
        self.verify.append((to, link))

    async def send_password_reset(self, *, to: str, link: str) -> None:
        self.reset.append((to, link))


def _token_from(link: str) -> str:
    return link.split("token=", 1)[1]


# --------------------------------------------------------------------------
#  Pure primitives (no DB) — always run
# --------------------------------------------------------------------------


async def test_password_is_argon2id_and_not_plaintext():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert h.startswith("$argon2id$")  # Argon2id, not a weaker variant
    assert verify_password(h, "correct horse battery staple") is True
    assert verify_password(h, "wrong password") is False
    # Two hashes of the same password differ (unique random salt each time).
    assert h != hash_password("correct horse battery staple")
    # Current policy hash needs no rehash; a foreign/garbage hash fails safe.
    assert needs_rehash(h) is False
    assert verify_password("not-a-hash", "x") is False


async def test_token_hash_is_deterministic_and_compare_is_constant_time():
    t = generate_token()
    assert t != generate_token()  # fresh entropy each call
    assert hash_token(t) == hash_token(t)  # deterministic lookup key
    assert hash_token(t) != t  # never store the raw token
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False


# --------------------------------------------------------------------------
#  DB-backed
# --------------------------------------------------------------------------


async def _new_user(
    s: AsyncSession, *, verified: bool = True, password: str = "sup3r-secret-pw"
) -> User:
    u = User(
        email=f"user-{_tag()}@example.test",
        password_hash=hash_password(password),
        email_verified_at=datetime.now(UTC) if verified else None,
        status="active",
    )
    s.add(u)
    await s.flush()
    return u


async def test_session_create_resolve_revoke_and_expire():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raw, row = await sessions.create_session(s, user_id=u.id, settings=settings)
            await s.commit()

            # Raw token resolves; a wrong token does not.
            got = await sessions.resolve_session(s, raw_token=raw)
            assert got is not None and got.id == row.id
            assert await sessions.resolve_session(s, raw_token="bogus") is None

            # Revocation kills it.
            await sessions.revoke_session(s, user_session=got)
            await s.commit()
            assert await sessions.resolve_session(s, raw_token=raw) is None

            # Expiry kills it (independently of revocation).
            raw2, row2 = await sessions.create_session(s, user_id=u.id, settings=settings)
            row2.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await s.commit()
            assert await sessions.resolve_session(s, raw_token=raw2) is None
    finally:
        await eng.dispose()


async def test_revoke_all_sessions_for_user():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raws = [
                (await sessions.create_session(s, user_id=u.id, settings=settings))[0]
                for _ in range(3)
            ]
            await s.commit()
            n = await sessions.revoke_all_for_user(s, user_id=u.id)
            await s.commit()
            assert n == 3
            for raw in raws:
                assert await sessions.resolve_session(s, raw_token=raw) is None
    finally:
        await eng.dispose()


async def test_email_token_is_single_use_and_expiring():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raw = await email_tokens.issue_token(s, user_id=u.id, purpose="reset", ttl_seconds=3600)
            await s.commit()

            # Wrong purpose is rejected.
            assert await email_tokens.consume_token(s, raw_token=raw, purpose="verify") is None
            # Correct purpose succeeds once.
            assert await email_tokens.consume_token(s, raw_token=raw, purpose="reset") == u.id
            await s.commit()
            # Reuse fails (single-use).
            assert await email_tokens.consume_token(s, raw_token=raw, purpose="reset") is None

            # Expired token fails.
            raw2 = await email_tokens.issue_token(s, user_id=u.id, purpose="verify", ttl_seconds=-1)
            await s.commit()
            assert await email_tokens.consume_token(s, raw_token=raw2, purpose="verify") is None

            # Issuing a fresh token invalidates the prior unspent one.
            first = await email_tokens.issue_token(
                s, user_id=u.id, purpose="reset", ttl_seconds=3600
            )
            second = await email_tokens.issue_token(
                s, user_id=u.id, purpose="reset", ttl_seconds=3600
            )
            await s.commit()
            assert await email_tokens.consume_token(s, raw_token=first, purpose="reset") is None
            assert await email_tokens.consume_token(s, raw_token=second, purpose="reset") == u.id
    finally:
        await eng.dispose()


async def test_signup_verify_signin_happy_path():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    cap = _CaptureSender()
    set_email_sender(cap)
    email = f"signup-{_tag()}@example.test"
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await service.signup(
                s, email=email, password="a-strong-password", display_name="Ann", settings=settings
            )
            await s.commit()

        # Unverified account cannot sign in yet.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            r = await service.signin(
                s, email=email, password="a-strong-password", settings=settings
            )
            await s.commit()
            assert r.ok is False

        # Verify via the emailed token, then sign in.
        assert cap.verify, "verification email should have been sent"
        token = _token_from(cap.verify[-1][1])
        async with AsyncSession(eng, expire_on_commit=False) as s:
            assert await service.verify_email(s, raw_token=token, settings=settings) is True
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            r = await service.signin(
                s, email=email, password="a-strong-password", settings=settings
            )
            await s.commit()
            assert r.ok and r.user and r.session_token
            # Wrong password is generic-fail.
            bad = await service.signin(s, email=email, password="nope", settings=settings)
            assert bad.ok is False
    finally:
        set_email_sender(
            __import__("aicmo.auth.email", fromlist=["LogEmailSender"]).LogEmailSender()
        )
        await eng.dispose()


async def test_duplicate_signup_does_not_create_second_user_or_change_password():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    set_email_sender(_CaptureSender())
    email = f"dup-{_tag()}@example.test"
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await service.signup(
                s, email=email, password="first-password-xx", display_name=None, settings=settings
            )
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            before = (await s.execute(select(User).where(User.email == email))).scalar_one()
            first_hash = before.password_hash
            # Second signup with the same email must NOT create a row or change the hash.
            await service.signup(
                s, email=email, password="attacker-chosen-pw", display_name=None, settings=settings
            )
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            rows = (await s.execute(select(User).where(User.email == email))).scalars().all()
            assert len(rows) == 1
            assert rows[0].password_hash == first_hash
    finally:
        set_email_sender(
            __import__("aicmo.auth.email", fromlist=["LogEmailSender"]).LogEmailSender()
        )
        await eng.dispose()


async def test_password_reset_revokes_all_sessions():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    cap = _CaptureSender()
    set_email_sender(cap)
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s)
            raw_sess, _ = await sessions.create_session(s, user_id=u.id, settings=settings)
            await s.commit()
            email = u.email

        async with AsyncSession(eng, expire_on_commit=False) as s:
            await service.request_password_reset(s, email=email, settings=settings)
            await s.commit()
        token = _token_from(cap.reset[-1][1])
        async with AsyncSession(eng, expire_on_commit=False) as s:
            assert (
                await service.reset_password(
                    s, raw_token=token, new_password="brand-new-password", settings=settings
                )
                is True
            )
            await s.commit()
        # Old session is dead; new password works.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            assert await sessions.resolve_session(s, raw_token=raw_sess) is None
            r = await service.signin(
                s, email=email, password="brand-new-password", settings=settings
            )
            await s.commit()
            assert r.ok is True
    finally:
        set_email_sender(
            __import__("aicmo.auth.email", fromlist=["LogEmailSender"]).LogEmailSender()
        )
        await eng.dispose()


async def test_change_password_revokes_other_sessions_only():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s, password="old-password-xx")
            keep_raw, keep_row = await sessions.create_session(s, user_id=u.id, settings=settings)
            other_raw, _ = await sessions.create_session(s, user_id=u.id, settings=settings)
            await s.commit()
            ok = await service.change_password(
                s,
                user=u,
                current_password="old-password-xx",
                new_password="new-password-yy",
                settings=settings,
                keep_session_id=keep_row.id,
            )
            await s.commit()
            assert ok is True
            # The kept session survives; the other is revoked.
            assert await sessions.resolve_session(s, raw_token=keep_raw) is not None
            assert await sessions.resolve_session(s, raw_token=other_raw) is None
            # Wrong current password is rejected.
            assert (
                await service.change_password(
                    s,
                    user=u,
                    current_password="WRONG",
                    new_password="whatever-zz-1",
                    settings=settings,
                )
                is False
            )
    finally:
        await eng.dispose()


async def test_login_throttle_locks_out_after_threshold():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            u = await _new_user(s, password="right-password-xx")
            ip = f"10.0.0.{uuid.uuid4().int % 250}"
            # Exhaust the per-account failure budget.
            for _ in range(settings.login_max_attempts_per_account):
                r = await service.signin(
                    s, email=u.email, password="wrong", settings=settings, ip=ip
                )
                assert r.ok is False and r.locked is False
            await s.commit()
            # Now even the CORRECT password is locked out.
            r = await service.signin(
                s, email=u.email, password="right-password-xx", settings=settings, ip=ip
            )
            assert r.locked is True and r.ok is False
    finally:
        await eng.dispose()
