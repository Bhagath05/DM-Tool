"""CRM email provider — DM Tool's own SMTP transport behind the EmailProvider
Protocol. Verifies provider selection is honest about configuration and that the
SMTP provider never fabricates delivery or raises into the caller. No network:
the SMTP transport is monkeypatched. No third-party provider.
"""

from __future__ import annotations

import pytest

from aicmo.modules.crm import email_providers as ep
from aicmo.modules.crm.email_providers import (
    EmailSendRequest,
    SmtpEmailProvider,
    StubEmailProvider,
    get_email_provider,
)


def _settings(monkeypatch, **over):
    from aicmo.config import get_settings

    s = get_settings()
    base = dict(smtp_host="", smtp_port=587, smtp_username="", smtp_password="", smtp_tls="starttls", smtp_from="")
    base.update(over)
    for k, v in base.items():
        monkeypatch.setattr(s, k, v, raising=False)
    monkeypatch.setattr(ep, "get_settings", lambda: s)
    return s


# ---- Provider selection ----------------------------------------------------
def test_defaults_to_stub_when_unconfigured(monkeypatch):
    _settings(monkeypatch)
    assert isinstance(get_email_provider(), StubEmailProvider)


def test_smtp_selected_when_configured(monkeypatch):
    _settings(monkeypatch, smtp_host="mail.dmtool.internal", smtp_from="DM Tool <no-reply@dm>")
    prov = get_email_provider()
    assert isinstance(prov, SmtpEmailProvider)
    assert prov.name == "smtp"


def test_incomplete_smtp_falls_back_to_stub(monkeypatch):
    # Host but no sender → must NOT pretend; fall back honestly to the stub.
    _settings(monkeypatch, smtp_host="mail.dmtool.internal", smtp_from="")
    assert isinstance(get_email_provider(), StubEmailProvider)


# ---- SMTP provider send behaviour (transport mocked) -----------------------
_REQ = EmailSendRequest(to_email="a@b.com", subject="Hi", html="<p>Hi</p>")


@pytest.mark.asyncio
async def test_send_success_is_queued_not_delivered(monkeypatch):
    sent: list = []

    async def _fake(settings, *, to, subject, html):
        sent.append((to, subject, html))

    monkeypatch.setattr("aicmo.email.smtp.send_email", _fake)
    _settings(monkeypatch, smtp_host="mail", smtp_from="n@x")
    result = await SmtpEmailProvider().send(_REQ)
    assert result.status == "queued"
    assert result.delivered is False  # delivery confirmed only by bounce/DSN
    assert sent == [("a@b.com", "Hi", "<p>Hi</p>")]


@pytest.mark.asyncio
async def test_send_delivery_failure_is_failed_not_raised(monkeypatch):
    from aicmo.email.smtp import SmtpDeliveryError

    async def _boom(settings, *, to, subject, html):
        raise SmtpDeliveryError("boom")

    monkeypatch.setattr("aicmo.email.smtp.send_email", _boom)
    _settings(monkeypatch, smtp_host="mail", smtp_from="n@x")
    result = await SmtpEmailProvider().send(_REQ)  # must not raise into the caller
    assert result.status == "failed"
    assert result.delivered is False


@pytest.mark.asyncio
async def test_send_unconfigured_is_failed_not_raised(monkeypatch):
    from aicmo.email.smtp import SmtpNotConfiguredError

    async def _nc(settings, *, to, subject, html):
        raise SmtpNotConfiguredError("nc")

    monkeypatch.setattr("aicmo.email.smtp.send_email", _nc)
    _settings(monkeypatch, smtp_host="mail", smtp_from="n@x")
    result = await SmtpEmailProvider().send(_REQ)
    assert result.status == "failed"
