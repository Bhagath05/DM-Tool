"""Operational alerting for terminal auth-email delivery failures.

An alert fires ONLY on a terminal state — a permanent failure or an exhausted
retry budget — never on an intermediate retry or a success. It reuses the shared
`aicmo.observability.alerts.alert` path, carries only safe operational context
(event, email type, job id, attempt, classification), and never carries a token,
URL, email address, SMTP credential, or user identifier. Alert-path failures are
swallowed and cannot affect the job.
"""

from __future__ import annotations

import uuid

import pytest
from arq import Retry

from aicmo.auth import tasks
from aicmo.auth.email_delivery import AUTH_EMAIL_MAX_TRIES
from aicmo.email.smtp import SmtpDeliveryError, SmtpNotConfiguredError


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


def _capture_alerts(monkeypatch) -> list:
    """Record calls to the shared alert path (the funnel lazy-imports it)."""
    captured: list = []

    async def fake_alert(message, *, level="error", **ctx):
        captured.append({"message": message, "level": level, **ctx})

    monkeypatch.setattr("aicmo.observability.alerts.alert", fake_alert)
    return captured


def _install_failing_send(monkeypatch, exc: BaseException) -> None:
    async def boom(session, **kwargs):
        raise exc

    monkeypatch.setattr(tasks, "_issue_and_send", boom)


# --- 1. Permanent failure emits the operational alert -----------------------
@pytest.mark.asyncio
async def test_permanent_failure_emits_alert(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpDeliveryError("5.7.1 rejected", transient=False))
    captured = _capture_alerts(monkeypatch)

    await tasks.send_auth_email({"job_id": "JOB-1", "job_try": 1}, str(uuid.uuid4()), "reset")

    assert len(captured) == 1
    a = captured[0]
    assert a["event"] == "auth.email.permanent_failure"
    assert a["classification"] == "permanent"
    assert a["email_type"] == "reset"
    assert a["job_id"] == "JOB-1"
    assert a["attempt"] == 1
    assert a["level"] == "error"


@pytest.mark.asyncio
async def test_unconfigured_smtp_emits_alert(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpNotConfiguredError("not configured"))
    captured = _capture_alerts(monkeypatch)

    await tasks.send_auth_email({"job_id": "JOB-C", "job_try": 1}, str(uuid.uuid4()), "verify")

    assert len(captured) == 1
    assert captured[0]["classification"] == "not_configured"
    assert captured[0]["event"] == "auth.email.permanent_failure"


# --- 2. Retry exhaustion emits the operational alert ------------------------
@pytest.mark.asyncio
async def test_retry_exhaustion_emits_alert(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpDeliveryError("temporary", transient=True))
    captured = _capture_alerts(monkeypatch)

    # Final permitted attempt: a transient failure now exhausts the budget.
    await tasks.send_auth_email(
        {"job_id": "JOB-2", "job_try": AUTH_EMAIL_MAX_TRIES}, str(uuid.uuid4()), "verify"
    )

    assert len(captured) == 1
    assert captured[0]["classification"] == "transient_exhausted"
    assert captured[0]["event"] == "auth.email.permanent_failure"
    assert captured[0]["attempt"] == AUTH_EMAIL_MAX_TRIES


# --- 3. Intermediate transient failure does NOT emit a terminal alert -------
@pytest.mark.asyncio
async def test_intermediate_retry_emits_no_alert(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpDeliveryError("temporary", transient=True))
    captured = _capture_alerts(monkeypatch)

    with pytest.raises(Retry):  # a retry is scheduled, not a terminal state
        await tasks.send_auth_email({"job_id": "JOB-3", "job_try": 1}, str(uuid.uuid4()), "verify")

    assert captured == []


# --- 4. Success emits no terminal failure alert -----------------------------
@pytest.mark.asyncio
async def test_success_emits_no_alert(monkeypatch):
    _install_worker_session(monkeypatch)

    async def ok(session, **kwargs):
        return True

    monkeypatch.setattr(tasks, "_issue_and_send", ok)
    captured = _capture_alerts(monkeypatch)

    # A late-but-successful attempt (as after transient retries) → no alert.
    await tasks.send_auth_email({"job_id": "JOB-4", "job_try": 3}, str(uuid.uuid4()), "verify")

    assert captured == []


# --- 5 + 6. Alert payload carries safe metadata and NO sensitive data -------
@pytest.mark.asyncio
async def test_alert_payload_is_safe(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpDeliveryError("perm", transient=False))
    captured = _capture_alerts(monkeypatch)

    uid = str(uuid.uuid4())
    await tasks.send_auth_email({"job_id": "JOB-5", "job_try": 1}, uid, "verify")

    a = captured[0]
    # Safe operational metadata present.
    for key in ("event", "email_type", "job_id", "attempt", "classification"):
        assert key in a
    # Nothing sensitive present anywhere in the payload.
    blob = repr(a).lower()
    assert uid.lower() not in blob  # no user identifier / PII in the alert
    assert "@" not in blob  # no email address
    assert "token" not in blob  # no verification/reset token
    assert "://" not in blob  # no reset/verification URL
    assert "password" not in blob  # no SMTP password / credential


# --- 7. Existing alert_job_failure behavior remains compatible --------------
@pytest.mark.asyncio
async def test_alert_job_failure_still_works():
    from aicmo.observability import alerts

    # No Slack webhook / Sentry DSN in tests → no-op, and must never raise.
    await alerts.alert_job_failure("send_auth_email", RuntimeError("boom"))


# --- 8. Alert-path failure must not break the job / auth semantics ----------
@pytest.mark.asyncio
async def test_alert_failure_does_not_break_job(monkeypatch):
    _install_worker_session(monkeypatch)
    _install_failing_send(monkeypatch, SmtpDeliveryError("perm", transient=False))

    async def exploding_alert(*a, **k):
        raise RuntimeError("alert backend down")

    monkeypatch.setattr("aicmo.observability.alerts.alert", exploding_alert)

    # Must complete cleanly despite the alert backend raising — the funnel
    # swallows it, so the delivery job (and auth flow) is unaffected.
    await tasks.send_auth_email({"job_id": "JOB-8", "job_try": 1}, str(uuid.uuid4()), "verify")
