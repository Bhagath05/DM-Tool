"""Auth transactional email delivery — sender selection + security invariants.

Covers: dev LogEmailSender, config-driven production selection, fail-closed
production guard, verification/reset delivery through the shared provider, and
the two security invariants that matter most for the production adapter — the
link/token is never logged, and the persisted token is a hash, never the raw.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aicmo.auth import email as auth_email
from aicmo.auth.email import (
    LogEmailSender,
    ProductionEmailSender,
    build_email_sender,
)
from aicmo.config import email_delivery_configured

_LINK = "https://app.example.com/verify-email?token=SUPER-SECRET-TOKEN-123"


def _cfg(provider="", api_key="", from_email=""):
    return SimpleNamespace(
        email_provider=provider, email_api_key=api_key, email_from=from_email
    )


# --- 1. Dev default: LogEmailSender is selected and it logs the link ---------
def test_dev_default_uses_log_sender():
    assert isinstance(build_email_sender(_cfg()), LogEmailSender)
    assert email_delivery_configured(_cfg()) is False


@pytest.mark.asyncio
async def test_log_sender_emits_link_to_log(monkeypatch):
    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    await LogEmailSender().send_verification(to="a@example.com", link=_LINK)
    # Dev channel intentionally logs the link so local flows are testable.
    kwargs = fake_log.info.call_args.kwargs
    assert kwargs.get("link") == _LINK and kwargs.get("delivery") == "log"


# --- 2/3. Config-driven selection -------------------------------------------
def test_production_config_selects_production_sender():
    cfg = _cfg(provider="resend", api_key="re_live_xxx", from_email="DM Tool <hi@x.com>")
    assert email_delivery_configured(cfg) is True
    assert isinstance(build_email_sender(cfg), ProductionEmailSender)


def test_incomplete_or_stub_provider_falls_back_to_log():
    # Selected but missing key/from → do NOT accidentally send; fall back to log.
    assert isinstance(build_email_sender(_cfg("resend", "", "hi@x.com")), LogEmailSender)
    assert isinstance(build_email_sender(_cfg("resend", "re_x", "")), LogEmailSender)
    # "stub"/unknown provider → log adapter.
    assert isinstance(build_email_sender(_cfg("stub")), LogEmailSender)
    assert isinstance(build_email_sender(_cfg("sendgrid", "k", "f@x.com")), LogEmailSender)


# --- 4. Production fail-closed when email is unconfigured --------------------
def test_missing_email_config_fails_closed_in_production(monkeypatch):
    from aicmo.config import get_settings, validate_production_secrets

    monkeypatch.setenv("API_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(get_settings())
    assert "Email delivery is not configured" in str(exc.value)
    get_settings.cache_clear()


# --- 5/6/7. Production sender delivers through the provider, never logs -------
class _CapturingProvider:
    name = "capture"

    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, request):
        from aicmo.modules.crm.email_providers import EmailSendResult

        self.sent.append(request)
        return EmailSendResult(
            provider="capture", message_id="m1", status="queued", delivered=False
        )


def _install_capturing_provider(monkeypatch) -> _CapturingProvider:
    cap = _CapturingProvider()
    monkeypatch.setattr(
        "aicmo.modules.crm.email_providers.get_email_provider", lambda: cap
    )
    return cap


@pytest.mark.asyncio
async def test_production_sender_sends_verification_through_provider(monkeypatch):
    cap = _install_capturing_provider(monkeypatch)
    await ProductionEmailSender().send_verification(to="user@example.com", link=_LINK)
    assert len(cap.sent) == 1
    req = cap.sent[0]
    assert req.to_email == "user@example.com"
    assert "verify" in req.subject.lower()
    assert _LINK in req.html  # the link travels only inside the email body


@pytest.mark.asyncio
async def test_production_sender_sends_password_reset_through_provider(monkeypatch):
    cap = _install_capturing_provider(monkeypatch)
    await ProductionEmailSender().send_password_reset(to="user@example.com", link=_LINK)
    assert len(cap.sent) == 1
    req = cap.sent[0]
    assert req.to_email == "user@example.com"
    assert "reset" in req.subject.lower()
    assert _LINK in req.html


@pytest.mark.asyncio
async def test_production_sender_never_logs_link_or_token(monkeypatch):
    _install_capturing_provider(monkeypatch)
    fake_log = MagicMock()
    monkeypatch.setattr(auth_email, "log", fake_log)
    await ProductionEmailSender().send_verification(to="user@example.com", link=_LINK)
    await ProductionEmailSender().send_password_reset(to="user@example.com", link=_LINK)
    # Inspect EVERY log call's args + kwargs — the link and its token must never
    # appear anywhere in the structured log for the production adapter.
    for call in fake_log.mock_calls:
        blob = repr(call)
        assert _LINK not in blob
        assert "SUPER-SECRET-TOKEN-123" not in blob


# --- 6 (persistence). Raw token is never stored — only its hash --------------
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
            row = (
                await s.execute(
                    text("SELECT token_hash FROM email_tokens WHERE user_id=:u"), {"u": user}
                )
            ).one()
        stored = row[0]
        assert stored == hash_token(raw)  # hash at rest
        assert stored != raw  # never the raw token
        assert raw not in stored
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM email_tokens WHERE user_id=:u"), {"u": user})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


# --- 8. Enumeration-safe responses unchanged --------------------------------
def test_enumeration_safe_messages_do_not_reveal_existence():
    from aicmo.auth.router import _RESET_OK, _SIGNUP_OK

    assert "If that email" in _SIGNUP_OK.message
    assert "If an account exists" in _RESET_OK.message
    # Must not assert or deny that the address is registered.
    for msg in (_SIGNUP_OK.message, _RESET_OK.message):
        low = msg.lower()
        assert "already registered" not in low
        assert "does not exist" not in low
        assert "no account" not in low
