"""Auth email suppression foundation — regression tests.

Covers: a terminal RECIPIENT rejection writes a suppression record and is
idempotent; a suppressed destination is skipped before a token is minted;
skipping stays enumeration-safe; transient/exhausted and successful deliveries
never suppress; an our-side "permanent" (auth/TLS/config) failure never
suppresses; suppression identity is the email so a new address is not blocked by
an old one; the record holds no secrets; token semantics and alerting are
unaffected. Mostly mocked; the DB write/idempotency is Postgres-gated.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from aicmo.auth import tasks
from aicmo.auth.email_delivery import (
    AUTH_EMAIL_MAX_TRIES,
    _issue_and_send,
    deliver_auth_email,
    note_permanent_auth_email_failure,
)
from aicmo.email.smtp import SmtpDeliveryError


def _settings(**over):
    base = dict(
        jobs_enabled=False,
        smtp_host="", smtp_port=587, smtp_username="", smtp_password="",
        smtp_tls="starttls", smtp_from="",
        email_verify_ttl_seconds=3600, password_reset_ttl_seconds=1800,
        public_base_url="https://app.example.test",
    )
    base.update(over)
    return SimpleNamespace(**base)


class _RecordingSender:
    def __init__(self):
        self.verify: list = []
        self.reset: list = []

    async def send_verification(self, *, to, link):
        self.verify.append((to, link))

    async def send_password_reset(self, *, to, link):
        self.reset.append((to, link))


class _Result:
    def __init__(self, hit: bool):
        self._hit = hit

    def first(self):
        return ("row",) if self._hit else None


class _Session:
    """Session whose .get returns a user and .execute answers the suppression
    lookup (suppressed toggled by the flag)."""

    def __init__(self, user, *, suppressed: bool = False):
        self._user = user
        self._suppressed = suppressed

    async def get(self, model, pk):
        return self._user

    async def execute(self, *a, **k):
        return _Result(self._suppressed)


class _WorkerSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _install_worker_session(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _WorkerSession())


def _capture_funnel(monkeypatch) -> list:
    calls: list = []

    async def fake_note(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(tasks, "note_permanent_auth_email_failure", fake_note)
    return calls


def _silence_alert(monkeypatch) -> None:
    async def noop(*a, **k):
        pass

    monkeypatch.setattr("aicmo.observability.alerts.alert", noop)


def _install_write_session(monkeypatch, user) -> None:
    class _WS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, model, pk):
            return user

        async def commit(self):
            pass

    monkeypatch.setattr("aicmo.db.session.SessionLocal", lambda: _WS())


# --- 1 + 8. Recipient rejection writes a suppression with no secrets ---------
@pytest.mark.asyncio
async def test_recipient_rejection_writes_suppression(monkeypatch):
    recorded: list = []

    async def fake_suppress(session, *, email, user_id, reason, source, meta=None):
        recorded.append({"email": email, "user_id": user_id, "reason": reason, "source": source, "meta": meta})

    monkeypatch.setattr("aicmo.auth.email_delivery.suppress_email", fake_suppress)
    _silence_alert(monkeypatch)
    user = SimpleNamespace(id=uuid.uuid4(), email="bounce@example.test")
    _install_write_session(monkeypatch, user)

    await note_permanent_auth_email_failure(
        purpose="verify", user_id=str(user.id),
        classification="recipient_rejected", recipient_rejected=True,
    )

    assert len(recorded) == 1
    r = recorded[0]
    assert r["email"] == "bounce@example.test"
    assert r["reason"] == "permanent_bounce"
    assert r["source"] == "auth_email_delivery"
    blob = repr(r).lower()
    assert "token" not in blob and "://" not in blob and "password" not in blob


# --- 5. Transient (exhausted) failure does not suppress ---------------------
@pytest.mark.asyncio
async def test_transient_exhausted_does_not_suppress(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("temporary", transient=True)

    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    calls = _capture_funnel(monkeypatch)

    await tasks.send_auth_email(
        {"job_id": "J", "job_try": AUTH_EMAIL_MAX_TRIES}, str(uuid.uuid4()), "verify"
    )
    assert calls and calls[0]["classification"] == "transient_exhausted"
    assert calls[0]["recipient_rejected"] is False


# --- (our-side permanent) auth/TLS/config never suppresses ------------------
@pytest.mark.asyncio
async def test_our_side_permanent_does_not_suppress(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("535 auth failed", transient=False, recipient_rejected=False)

    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    calls = _capture_funnel(monkeypatch)

    await tasks.send_auth_email({"job_id": "J", "job_try": 1}, str(uuid.uuid4()), "reset")
    assert calls and calls[0]["classification"] == "permanent"
    assert calls[0]["recipient_rejected"] is False


# --- (classification) recipient rejection forwards the suppress signal -------
@pytest.mark.asyncio
async def test_worker_recipient_rejection_classifies_and_forwards(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("550 mailbox unavailable", transient=False, recipient_rejected=True)

    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    calls = _capture_funnel(monkeypatch)

    await tasks.send_auth_email({"job_id": "J", "job_try": 1}, str(uuid.uuid4()), "verify")
    assert calls and calls[0]["classification"] == "recipient_rejected"
    assert calls[0]["recipient_rejected"] is True


# --- 6. Successful delivery does not suppress -------------------------------
@pytest.mark.asyncio
async def test_success_does_not_suppress(monkeypatch):
    _install_worker_session(monkeypatch)

    async def ok(session, **k):
        return True

    monkeypatch.setattr(tasks, "_issue_and_send", ok)
    calls = _capture_funnel(monkeypatch)

    await tasks.send_auth_email({"job_id": "J", "job_try": 1}, str(uuid.uuid4()), "verify")
    assert calls == []


# --- 3 + 9. Suppressed address is skipped BEFORE a token is minted ----------
@pytest.mark.asyncio
async def test_suppressed_address_is_skipped(monkeypatch):
    issued: list = []

    async def fake_issue(session, *, user_id, purpose, ttl_seconds):
        issued.append(1)
        return "TK"

    monkeypatch.setattr("aicmo.auth.email_tokens.issue_token", fake_issue)
    user = SimpleNamespace(id=uuid.uuid4(), email="bad@example.test")
    sender = _RecordingSender()

    out = await _issue_and_send(
        _Session(user, suppressed=True), user_id=user.id, purpose="verify",
        settings=_settings(), sender=sender,
    )
    assert out is True  # handled — nothing to retry
    assert sender.verify == [] and sender.reset == []  # not sent
    assert issued == []  # no token minted for a suppressed destination


# --- 4. Suppressed delivery stays enumeration-safe (no raise, no send) ------
@pytest.mark.asyncio
async def test_suppressed_delivery_is_enumeration_safe(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), email="bad@example.test")
    rec = _RecordingSender()
    monkeypatch.setattr("aicmo.auth.email_delivery.get_email_sender", lambda: rec)

    # Sync path (pool None) with a suppressed user: returns without raising and
    # sends nothing, so the HTTP handler still returns its generic response.
    await deliver_auth_email(
        _Session(user, suppressed=True), None, user_id=user.id, purpose="reset", settings=_settings()
    )
    assert rec.reset == []


# --- 7. A non-suppressed (e.g. changed) address is delivered ----------------
@pytest.mark.asyncio
async def test_unsuppressed_address_is_delivered(monkeypatch):
    issued: list = []

    async def fake_issue(session, *, user_id, purpose, ttl_seconds):
        issued.append(1)
        return "TK"

    monkeypatch.setattr("aicmo.auth.email_tokens.issue_token", fake_issue)
    user = SimpleNamespace(id=uuid.uuid4(), email="new@example.test")
    sender = _RecordingSender()

    out = await _issue_and_send(
        _Session(user, suppressed=False), user_id=user.id, purpose="verify",
        settings=_settings(), sender=sender,
    )
    assert out is True and sender.verify  # delivered to the current (unsuppressed) address


# --- 10. Recipient rejection still fires the operational alert --------------
@pytest.mark.asyncio
async def test_recipient_rejection_still_alerts(monkeypatch):
    alerts: list = []

    async def fake_alert(message, *, level="error", **ctx):
        alerts.append({"message": message, "level": level, **ctx})

    monkeypatch.setattr("aicmo.observability.alerts.alert", fake_alert)

    async def fake_suppress(session, **k):
        pass

    monkeypatch.setattr("aicmo.auth.email_delivery.suppress_email", fake_suppress)
    user = SimpleNamespace(id=uuid.uuid4(), email="bounce@example.test")
    _install_write_session(monkeypatch, user)

    await note_permanent_auth_email_failure(
        purpose="verify", user_id=str(user.id),
        classification="recipient_rejected", recipient_rejected=True,
    )
    assert len(alerts) == 1
    assert alerts[0]["classification"] == "recipient_rejected"
    assert alerts[0]["event"] == "auth.email.permanent_failure"
    # The alert must not carry the email address or user id.
    blob = repr(alerts[0]).lower()
    assert "@" not in blob and str(user.id) not in blob


# --- 1 + 2 + 7 + 8 (integration). DB write is idempotent + email-keyed ------
@pytest.mark.asyncio
async def test_suppression_create_idempotent_and_email_keyed():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aicmo.auth.suppression import is_email_suppressed, suppress_email
    from aicmo.modules.users.models import User  # noqa: F401 — register FK target

    eng = create_async_engine(async_dsn())
    uid = uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    bad = f"bad-{tag}@example.test"
    fresh = f"fresh-{tag}@example.test"
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": uid, "e": bad},
            )
            # Two permanent-failure events for the same address → one row.
            await suppress_email(s, email=bad, user_id=uid, reason="permanent_bounce", source="auth_email_delivery")
            await suppress_email(s, email=bad.upper(), user_id=uid, reason="permanent_bounce", source="auth_email_delivery")
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            count = (
                await s.execute(
                    text("SELECT count(*) FROM email_suppressions WHERE email=:e"), {"e": bad}
                )
            ).scalar_one()
            assert count == 1  # idempotent (normalized, upsert)
            assert await is_email_suppressed(s, bad) is True
            assert await is_email_suppressed(s, bad.upper()) is True  # normalization
            # A different (e.g. changed) address is NOT blocked.
            assert await is_email_suppressed(s, fresh) is False
            # The stored row holds no token/URL/credential.
            row = (
                await s.execute(
                    text("SELECT reason, source, meta::text FROM email_suppressions WHERE email=:e"),
                    {"e": bad},
                )
            ).one()
            blob = repr(row).lower()
            assert "token" not in blob and "://" not in blob and "password" not in blob
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM email_suppressions WHERE user_id=:u"), {"u": uid})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
        await eng.dispose()
