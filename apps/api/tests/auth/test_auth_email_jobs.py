"""Resilient auth-email delivery via ARQ — regression tests.

Covers the required properties: auth email is queued (not sent in-request), the
worker sends, transient failures retry with a BOUNDED budget, permanent failures
do not retry, the Redis payload never carries a token/URL/email/SMTP-credential,
the token/link is never logged on the SMTP path, verification/reset security
semantics are unchanged, HTTP stays enumeration-safe when delivery has issues,
retried re-issues keep a single valid token, and the dev LogEmailSender still
logs the link. No real Redis; a couple of DB-semantics tests are Postgres-gated.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from arq import Retry

from aicmo.auth import tasks
from aicmo.auth.email_delivery import (
    AUTH_EMAIL_MAX_TRIES,
    _issue_and_send,
    backoff_seconds,
    deliver_auth_email,
)
from aicmo.email.smtp import SmtpDeliveryError, SmtpNotConfiguredError


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
    """An EmailSender that records (to, link) instead of delivering."""

    def __init__(self):
        self.verify: list = []
        self.reset: list = []

    async def send_verification(self, *, to, link):
        self.verify.append((to, link))

    async def send_password_reset(self, *, to, link):
        self.reset.append((to, link))


class _FakePool:
    def __init__(self, fail: bool = False):
        self.jobs: list = []
        self._fail = fail

    async def enqueue_job(self, function, *args, **kwargs):
        if self._fail:
            raise RuntimeError("redis unavailable")
        self.jobs.append((function, args, kwargs))
        return object()


class _GetSession:
    """Minimal session whose .get returns a fixed user."""

    def __init__(self, user):
        self._user = user

    async def get(self, model, pk):
        return self._user


class _WorkerSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _install_worker_session(monkeypatch) -> _WorkerSession:
    sess = _WorkerSession()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: sess)
    return sess


def _record_terminal(monkeypatch, store: list) -> None:
    """Replace the terminal-failure funnel (now async) with an async recorder."""

    async def _rec(**kwargs):
        store.append(kwargs)

    monkeypatch.setattr(tasks, "note_permanent_auth_email_failure", _rec)


# --- 1. Auth email is queued, not sent synchronously ------------------------
@pytest.mark.asyncio
async def test_auth_email_is_enqueued_not_sent_sync(monkeypatch):
    pool = _FakePool()
    rec = _RecordingSender()
    monkeypatch.setattr("aicmo.auth.email_delivery.get_email_sender", lambda: rec)
    await deliver_auth_email(object(), pool, user_id=uuid.uuid4(), purpose="verify", settings=_settings(jobs_enabled=True))
    assert len(pool.jobs) == 1 and pool.jobs[0][0] == "send_auth_email"
    assert rec.verify == [] and rec.reset == []  # nothing sent in the request path


# --- 6. SMTP credentials / token / email are never in the job payload -------
@pytest.mark.asyncio
async def test_job_payload_carries_only_id_and_purpose(monkeypatch):
    pool = _FakePool()
    settings = _settings(
        jobs_enabled=True, smtp_host="mail.x", smtp_from="a@x",
        smtp_username="smtp-login-zzz", smtp_password="pw-never-log-999",
    )
    uid = uuid.uuid4()
    await deliver_auth_email(object(), pool, user_id=uid, purpose="reset", settings=settings)
    fn, args, kwargs = pool.jobs[0]
    assert fn == "send_auth_email"
    assert args == (str(uid), "reset")  # ONLY the internal id + purpose
    assert kwargs == {}
    blob = repr((fn, args, kwargs))
    for secret in ("pw-never-log-999", "smtp-login-zzz"):
        assert secret not in blob


# --- 2. Worker successfully sends -------------------------------------------
@pytest.mark.asyncio
async def test_worker_sends_successfully(monkeypatch):
    sess = _install_worker_session(monkeypatch)

    async def ok(session, *, user_id, purpose, settings, sender):
        return True

    monkeypatch.setattr(tasks, "_issue_and_send", ok)
    await tasks.send_auth_email({"job_id": "j", "job_try": 1}, str(uuid.uuid4()), "verify")
    assert sess.committed is True


# --- 3. Transient SMTP failure retries --------------------------------------
@pytest.mark.asyncio
async def test_transient_failure_schedules_retry(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("temporary", transient=True)

    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    with pytest.raises(Retry):
        await tasks.send_auth_email({"job_id": "j", "job_try": 1}, str(uuid.uuid4()), "verify")


# --- 4. Retry count is bounded (no infinite retry) --------------------------
@pytest.mark.asyncio
async def test_retry_is_bounded(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("temporary", transient=True)

    recorded: list = []
    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    _record_terminal(monkeypatch, recorded)
    # On the final permitted attempt a transient failure must NOT raise Retry.
    await tasks.send_auth_email({"job_id": "j", "job_try": AUTH_EMAIL_MAX_TRIES}, str(uuid.uuid4()), "verify")
    assert recorded and recorded[-1]["classification"] == "transient_exhausted"


# --- 5. Permanent SMTP failure does not retry -------------------------------
@pytest.mark.asyncio
async def test_permanent_failure_does_not_retry(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpDeliveryError("permanent", transient=False)

    recorded: list = []
    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    _record_terminal(monkeypatch, recorded)
    # Even on the FIRST attempt, a permanent failure must not schedule a retry.
    await tasks.send_auth_email({"job_id": "j", "job_try": 1}, str(uuid.uuid4()), "reset")
    assert recorded and recorded[-1]["classification"] == "permanent"


@pytest.mark.asyncio
async def test_unconfigured_smtp_is_permanent(monkeypatch):
    _install_worker_session(monkeypatch)

    async def boom(session, **k):
        raise SmtpNotConfiguredError("not configured")

    recorded: list = []
    monkeypatch.setattr(tasks, "_issue_and_send", boom)
    _record_terminal(monkeypatch, recorded)
    await tasks.send_auth_email({"job_id": "j", "job_try": 1}, str(uuid.uuid4()), "verify")
    assert recorded and recorded[-1]["classification"] == "not_configured"


# --- (commit race) user not visible → bounded retry, then give up ------------
@pytest.mark.asyncio
async def test_user_not_visible_retries_then_gives_up(monkeypatch):
    _install_worker_session(monkeypatch)

    async def missing(session, **k):
        return False

    monkeypatch.setattr(tasks, "_issue_and_send", missing)
    with pytest.raises(Retry):  # early attempt → retry (row may be uncommitted)
        await tasks.send_auth_email({"job_id": "j", "job_try": 1}, str(uuid.uuid4()), "verify")
    # Final attempt → no infinite retry; completes without raising.
    await tasks.send_auth_email({"job_id": "j", "job_try": AUTH_EMAIL_MAX_TRIES}, str(uuid.uuid4()), "verify")


# --- backoff is exponential and bounded -------------------------------------
def test_backoff_is_exponential_and_capped():
    assert backoff_seconds(1) == 30
    assert backoff_seconds(2) == 60
    assert backoff_seconds(3) == 120
    assert backoff_seconds(10) == 900  # capped
    assert backoff_seconds(1) < backoff_seconds(4) <= 900


# --- 7. Token / link never logged on the SMTP (worker) path -----------------
@pytest.mark.asyncio
async def test_smtp_worker_sender_never_logs_token(monkeypatch):
    from aicmo.auth import email as auth_email

    async def fake_send(settings, *, to, subject, html):
        return None

    monkeypatch.setattr("aicmo.email.smtp.send_email", fake_send)
    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    secret_link = "https://app.example.test/verify-email?token=SECRET-TKN-777"
    sender = auth_email.SelfHostedSMTPEmailSender(raising=True)  # the worker's sender kind
    await sender.send_verification(to="u@example.test", link=secret_link)
    await sender.send_password_reset(to="u@example.test", link=secret_link.replace("verify-email", "reset-password"))
    for call in fake_log.mock_calls:
        assert "SECRET-TKN-777" not in repr(call)


# --- 8. Verification/reset security semantics unchanged ----------------------
@pytest.mark.asyncio
async def test_issue_and_send_purpose_ttl_and_db_recipient(monkeypatch):
    issued: list = []

    async def fake_issue(session, *, user_id, purpose, ttl_seconds):
        issued.append((user_id, purpose, ttl_seconds))
        return "RAW-TOKEN-123"

    monkeypatch.setattr("aicmo.auth.email_tokens.issue_token", fake_issue)
    user = SimpleNamespace(email="db-user@example.test")
    sender = _RecordingSender()
    settings = _settings(email_verify_ttl_seconds=111, password_reset_ttl_seconds=222)
    uid = uuid.uuid4()

    await _issue_and_send(_GetSession(user), user_id=uid, purpose="verify", settings=settings, sender=sender)
    assert issued[-1] == (uid, "verify", 111)  # correct purpose + ttl
    assert sender.verify[-1][0] == "db-user@example.test"  # recipient came from the DB row
    assert "RAW-TOKEN-123" in sender.verify[-1][1]  # token rides only inside the link

    await _issue_and_send(_GetSession(user), user_id=uid, purpose="reset", settings=settings, sender=sender)
    assert issued[-1] == (uid, "reset", 222)
    assert "RAW-TOKEN-123" in sender.reset[-1][1]


@pytest.mark.asyncio
async def test_issue_and_send_rejects_unknown_purpose():
    with pytest.raises(ValueError):
        await _issue_and_send(
            _GetSession(SimpleNamespace(email="x@y")), user_id=uuid.uuid4(),
            purpose="password_change", settings=_settings(), sender=_RecordingSender(),
        )


# --- 9. Enumeration-safe: delivery issues never surface into the response ----
@pytest.mark.asyncio
async def test_enqueue_failure_falls_back_and_never_raises(monkeypatch):
    pool = _FakePool(fail=True)  # enqueue_job raises
    rec = _RecordingSender()
    monkeypatch.setattr("aicmo.auth.email_delivery.get_email_sender", lambda: rec)

    async def fake_issue(session, *, user_id, purpose, ttl_seconds):
        return "TK"

    monkeypatch.setattr("aicmo.auth.email_tokens.issue_token", fake_issue)
    user = SimpleNamespace(email="u@example.test")
    # Must not raise — falls back to synchronous best-effort delivery.
    await deliver_auth_email(_GetSession(user), pool, user_id=uuid.uuid4(), purpose="verify", settings=_settings(jobs_enabled=True))
    assert rec.verify  # delivered via the fallback


def test_enumeration_safe_response_constants_unchanged():
    from aicmo.auth.router import _RESET_OK, _SIGNUP_OK

    assert "If that email" in _SIGNUP_OK.message
    assert "If an account exists" in _RESET_OK.message


# --- 11. Dev LogEmailSender behavior preserved (intentionally logs the link) --
@pytest.mark.asyncio
async def test_dev_log_sender_still_logs_link(monkeypatch):
    from aicmo.auth import email as auth_email

    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    monkeypatch.setattr("aicmo.auth.email_delivery.get_email_sender", lambda: auth_email.LogEmailSender())

    async def fake_issue(session, *, user_id, purpose, ttl_seconds):
        return "DEV-LINK-TOKEN"

    monkeypatch.setattr("aicmo.auth.email_tokens.issue_token", fake_issue)
    user = SimpleNamespace(email="dev@example.test")
    # pool None → synchronous fallback → LogEmailSender (dev channel) logs the link.
    await deliver_auth_email(_GetSession(user), None, user_id=uuid.uuid4(), purpose="verify", settings=_settings())
    assert "DEV-LINK-TOKEN" in repr(fake_log.info.call_args_list)


# --- 10. Retried re-issue keeps a single valid token (Postgres-gated) --------
@pytest.mark.asyncio
async def test_retry_reissue_keeps_single_valid_token():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aicmo.auth import email_tokens
    from aicmo.modules.users.models import User  # noqa: F401 — register FK target

    eng = create_async_engine(async_dsn())
    uid = uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    settings = _settings()
    sender = _RecordingSender()

    def _token(link: str) -> str:
        return link.split("token=")[-1]

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": uid, "e": f"{tag}@example.test"},
            )
            # First issue, then a retry that re-issues for the same user+purpose.
            await _issue_and_send(s, user_id=uid, purpose="verify", settings=settings, sender=sender)
            await _issue_and_send(s, user_id=uid, purpose="verify", settings=settings, sender=sender)
            await s.commit()

        first_raw = _token(sender.verify[0][1])
        second_raw = _token(sender.verify[1][1])
        assert first_raw != second_raw

        async with AsyncSession(eng, expire_on_commit=False) as s:
            unspent = (
                await s.execute(
                    text("SELECT count(*) FROM email_tokens WHERE user_id=:u AND used_at IS NULL"),
                    {"u": uid},
                )
            ).scalar_one()
            assert unspent == 1  # only the latest token is live — no inconsistent state

        # The superseded first token is invalid; the second consumes exactly once.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            assert await email_tokens.consume_token(s, raw_token=first_raw, purpose="verify") is None
            assert await email_tokens.consume_token(s, raw_token=second_raw, purpose="verify") == uid
            assert await email_tokens.consume_token(s, raw_token=second_raw, purpose="verify") is None
            await s.commit()
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM email_tokens WHERE user_id=:u"), {"u": uid})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
        await eng.dispose()
