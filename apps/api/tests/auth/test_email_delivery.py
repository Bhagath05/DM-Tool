"""Auth transactional email — self-hosted SMTP delivery + security invariants.

Covers: dev LogEmailSender, config-driven SMTP selection, fail-closed production
guard (SMTP + TLS), verification/reset delivery through DM Tool's own SMTP
transport, TLS handling (STARTTLS/implicit/no-downgrade), and the invariants
that matter — link/token never logged, SMTP credentials never logged, persisted
token hashed (never raw), enumeration-safe responses, and a test-injected sender
not being clobbered by app import. No third-party provider; SMTP is mocked.
"""

from __future__ import annotations

import smtplib
import uuid
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from aicmo.auth import email as auth_email
from aicmo.auth.email import (
    LogEmailSender,
    SelfHostedSMTPEmailSender,
    build_email_sender,
    get_email_sender,
    set_email_sender,
)
from aicmo.email import smtp as smtp_mod
from aicmo.email.smtp import (
    SmtpDeliveryError,
    SmtpNotConfiguredError,
    smtp_configured,
    smtp_production_problems,
)

_LINK = "https://app.example.com/verify-email?token=SUPER-SECRET-TOKEN-123"
_SECRET_PW = "smtp-p@ssw0rd-never-log"


def _cfg(host="", from_addr="", username="", password="", tls="starttls", port=587):
    return SimpleNamespace(
        smtp_host=host, smtp_port=port, smtp_username=username,
        smtp_password=password, smtp_tls=tls, smtp_from=from_addr,
    )


# --- 1/2. Dev default: LogEmailSender selected, logs the link ----------------
def test_dev_default_uses_log_sender():
    assert isinstance(build_email_sender(_cfg()), LogEmailSender)
    assert smtp_configured(_cfg()) is False


@pytest.mark.asyncio
async def test_log_sender_emits_link_to_log(monkeypatch):
    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    await LogEmailSender().send_verification(to="a@example.com", link=_LINK)
    kwargs = fake_log.info.call_args.kwargs
    assert kwargs.get("link") == _LINK and kwargs.get("delivery") == "log"


# --- 3/4. Config-driven SMTP selection --------------------------------------
def test_smtp_config_selects_self_hosted_smtp_sender():
    cfg = _cfg(host="mail.dmtool.internal", from_addr="DM Tool <no-reply@dmtool.app>")
    assert smtp_configured(cfg) is True
    assert isinstance(build_email_sender(cfg), SelfHostedSMTPEmailSender)


def test_incomplete_smtp_falls_back_to_log():
    assert isinstance(build_email_sender(_cfg(host="mail.x", from_addr="")), LogEmailSender)
    assert isinstance(build_email_sender(_cfg(host="", from_addr="f@x")), LogEmailSender)


# --- 5/6. Production fail-closed (SMTP required + TLS required) --------------
def test_missing_smtp_fails_closed_in_production(monkeypatch):
    from aicmo.config import get_settings, validate_production_secrets

    monkeypatch.setenv("API_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(get_settings())
    assert "SMTP" in str(exc.value)
    get_settings.cache_clear()


def test_production_rejects_non_tls_smtp():
    problems = smtp_production_problems(_cfg(host="h", from_addr="f@x", tls="none"))
    assert any("TLS" in p for p in problems)
    # Fully configured + TLS → no problems.
    assert smtp_production_problems(_cfg(host="h", from_addr="f@x", tls="starttls")) == []


# --- 7/8/9. Delivery through SMTP; link/token never logged -------------------
def _patch_send_email(monkeypatch) -> list:
    sent: list = []

    async def _fake_send(settings, *, to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr("aicmo.email.smtp.send_email", _fake_send)
    return sent


@pytest.mark.asyncio
async def test_verification_delivered_through_smtp(monkeypatch):
    sent = _patch_send_email(monkeypatch)
    await SelfHostedSMTPEmailSender().send_verification(to="user@example.com", link=_LINK)
    assert len(sent) == 1
    assert sent[0]["to"] == "user@example.com"
    assert "verify" in sent[0]["subject"].lower()
    assert _LINK in sent[0]["html"]  # link travels only inside the message body


@pytest.mark.asyncio
async def test_password_reset_delivered_through_smtp(monkeypatch):
    sent = _patch_send_email(monkeypatch)
    await SelfHostedSMTPEmailSender().send_password_reset(to="user@example.com", link=_LINK)
    assert len(sent) == 1 and "reset" in sent[0]["subject"].lower()
    assert _LINK in sent[0]["html"]


@pytest.mark.asyncio
async def test_smtp_sender_never_logs_link_or_token(monkeypatch):
    _patch_send_email(monkeypatch)
    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    await SelfHostedSMTPEmailSender().send_verification(to="user@example.com", link=_LINK)
    await SelfHostedSMTPEmailSender().send_password_reset(to="user@example.com", link=_LINK)
    for call in fake_log.mock_calls:
        blob = repr(call)
        assert _LINK not in blob and "SUPER-SECRET-TOKEN-123" not in blob


# --- 11/12/13. SMTP TLS handling (mocked transport, no network) -------------
class _FakeSMTP:
    instances: ClassVar[list] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls: list = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"], msg["Subject"]))


@pytest.mark.asyncio
async def test_smtp_starttls_and_login(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = _cfg(host="mail.x", from_addr="DM <n@x>", username="u", password=_SECRET_PW)
    await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")
    inst = _FakeSMTP.instances[-1]
    assert "starttls" in inst.calls  # TLS upgrade happened
    assert ("login", "u", _SECRET_PW) in inst.calls
    assert any(c[0] == "send" for c in inst.calls if isinstance(c, tuple))


@pytest.mark.asyncio
async def test_smtp_implicit_tls_uses_smtp_ssl(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    cfg = _cfg(host="mail.x", from_addr="DM <n@x>", tls="tls", port=465)
    await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")
    assert _FakeSMTP.instances and _FakeSMTP.instances[-1].port == 465


@pytest.mark.asyncio
async def test_smtp_starttls_never_downgrades(monkeypatch):
    class _NoTLS(_FakeSMTP):
        def starttls(self, context=None):
            raise smtplib.SMTPNotSupportedError("STARTTLS not supported")

    monkeypatch.setattr(smtplib, "SMTP", _NoTLS)
    cfg = _cfg(host="mail.x", from_addr="DM <n@x>")
    with pytest.raises(SmtpDeliveryError):
        await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")


@pytest.mark.asyncio
async def test_smtp_credentials_never_logged(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    fake_log = MagicMock()
    monkeypatch.setattr(smtp_mod, "log", fake_log)
    cfg = _cfg(host="mail.x", from_addr="DM <n@x>", username="secret-user", password=_SECRET_PW)
    await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")
    for call in fake_log.mock_calls:
        blob = repr(call)
        assert _SECRET_PW not in blob and "secret-user" not in blob


@pytest.mark.asyncio
async def test_authenticated_smtp_rejects_plaintext_tls_none(monkeypatch):
    # Credentials must NEVER cross a plaintext connection: tls=none + a
    # username/password is refused BEFORE any socket is opened.
    def _no_connect(*a, **k):
        raise AssertionError("must not open an SMTP connection for tls=none + credentials")

    monkeypatch.setattr(smtplib, "SMTP", _no_connect)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _no_connect)
    cfg = _cfg(host="mail.x", from_addr="DM <n@x>", username="u", password=_SECRET_PW, tls="none")
    with pytest.raises(SmtpNotConfiguredError):
        await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")


@pytest.mark.asyncio
async def test_unauthenticated_smtp_tls_none_still_allowed(monkeypatch):
    # A trusted unauthenticated local/private relay may still use tls=none —
    # the refusal above is scoped to authenticated sends only.
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    cfg = _cfg(host="localhost", from_addr="DM <n@x>", tls="none")  # no credentials
    await smtp_mod.send_email(cfg, to="r@x", subject="s", html="<p>hi</p>")
    inst = _FakeSMTP.instances[-1]
    assert "starttls" not in inst.calls  # no TLS negotiated on a trusted local relay
    assert any(isinstance(c, tuple) and c[0] == "send" for c in inst.calls)


# --- 6 (persistence). Raw token never stored — only its hash -----------------
@pytest.mark.asyncio
async def test_issue_token_persists_hash_not_raw():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aicmo.auth.email_tokens import issue_token
    from aicmo.auth.tokens import hash_token
    from aicmo.modules.users.models import User  # noqa: F401 — register FK target table

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    user = uuid.uuid4()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": user, "e": f"{tag}@example.com"},
            )
            raw = await issue_token(s, user_id=user, purpose="verify", ttl_seconds=3600)
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            stored = (
                await s.execute(
                    text("SELECT token_hash FROM email_tokens WHERE user_id=:u"), {"u": user}
                )
            ).one()[0]
        assert stored == hash_token(raw) and stored != raw and raw not in stored
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM email_tokens WHERE user_id=:u"), {"u": user})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


# --- 8 (isolation). App import must NOT overwrite a test-injected sender ------
def test_app_import_does_not_overwrite_injected_sender():
    sentinel = LogEmailSender()
    set_email_sender(sentinel)
    import aicmo.main  # noqa: F401 — importing the app must not mutate the sender
    assert get_email_sender() is sentinel


# --- Enumeration-safe responses unchanged -----------------------------------
def test_enumeration_safe_messages_do_not_reveal_existence():
    from aicmo.auth.router import _RESET_OK, _SIGNUP_OK

    assert "If that email" in _SIGNUP_OK.message
    assert "If an account exists" in _RESET_OK.message
    for msg in (_SIGNUP_OK.message, _RESET_OK.message):
        low = msg.lower()
        assert "already registered" not in low and "does not exist" not in low
