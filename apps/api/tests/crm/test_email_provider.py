"""Wave 0 #4 — real email delivery behind the existing EmailProvider Protocol.

Verifies provider selection (stub vs Resend) is honest about configuration, and
that the Resend provider builds the right request and never fabricates delivery
or raises into the caller. No network: httpx is monkeypatched.
"""

from __future__ import annotations

import pytest

from aicmo.modules.crm import email_providers as ep
from aicmo.modules.crm.email_providers import (
    EmailSendRequest,
    ResendEmailProvider,
    StubEmailProvider,
    get_email_provider,
)


class _FakeResp:
    def __init__(self, status_code: int, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = str(self._body)

    def json(self) -> dict:
        return self._body


class _FakeClient:
    """Minimal async httpx.AsyncClient stand-in."""

    def __init__(self, resp=None, raise_exc=None) -> None:
        self._resp = resp
        self._raise = raise_exc
        self.last_call: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.last_call = {"url": url, "headers": headers, "json": json}
        if self._raise:
            raise self._raise
        return self._resp


def _patch_httpx(monkeypatch, client: _FakeClient) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)


# ---------------------------------------------------------------------
#  Provider selection
# ---------------------------------------------------------------------


def _settings(monkeypatch, **over):
    from aicmo.config import get_settings

    s = get_settings()
    for k, v in over.items():
        monkeypatch.setattr(s, k, v, raising=False)
    monkeypatch.setattr(ep, "get_settings", lambda: s)
    return s


def test_defaults_to_stub_when_unconfigured(monkeypatch):
    _settings(monkeypatch, email_provider="")
    assert isinstance(get_email_provider(), StubEmailProvider)


def test_resend_selected_when_fully_configured(monkeypatch):
    _settings(
        monkeypatch,
        email_provider="resend",
        email_api_key="re_test_key",
        email_from="DM Tool <hi@x.com>",
    )
    prov = get_email_provider()
    assert isinstance(prov, ResendEmailProvider)
    assert prov.name == "resend"


def test_resend_selected_but_incomplete_falls_back_to_stub(monkeypatch):
    # Provider named but no key/sender → must NOT pretend; fall back honestly.
    _settings(monkeypatch, email_provider="resend", email_api_key="", email_from="")
    assert isinstance(get_email_provider(), StubEmailProvider)


def test_unsupported_provider_falls_back_to_stub(monkeypatch):
    _settings(monkeypatch, email_provider="carrier-pigeon")
    assert isinstance(get_email_provider(), StubEmailProvider)


# ---------------------------------------------------------------------
#  Resend send behaviour
# ---------------------------------------------------------------------

_REQ = EmailSendRequest(to_email="a@b.com", subject="Hi", html="<p>Hi</p>")


@pytest.mark.asyncio
async def test_send_success_is_queued_not_delivered(monkeypatch):
    client = _FakeClient(resp=_FakeResp(200, {"id": "msg_123"}))
    _patch_httpx(monkeypatch, client)
    prov = ResendEmailProvider(api_key="re_k", from_email="hi@x.com")

    result = await prov.send(_REQ)

    assert result.status == "queued"
    assert result.delivered is False  # delivery confirmed only by webhook
    assert result.message_id == "msg_123"
    # Correct auth + payload shape.
    assert client.last_call["headers"]["Authorization"] == "Bearer re_k"
    assert client.last_call["json"]["to"] == ["a@b.com"]
    assert client.last_call["json"]["from"] == "hi@x.com"


@pytest.mark.asyncio
async def test_send_rejection_is_failed_not_raised(monkeypatch):
    client = _FakeClient(resp=_FakeResp(422, {"error": "bad from"}))
    _patch_httpx(monkeypatch, client)
    prov = ResendEmailProvider(api_key="re_k", from_email="hi@x.com")

    result = await prov.send(_REQ)  # must not raise
    assert result.status == "failed"
    assert result.delivered is False


@pytest.mark.asyncio
async def test_send_transport_error_is_failed_not_raised(monkeypatch):
    import httpx

    client = _FakeClient(raise_exc=httpx.ConnectError("boom"))
    _patch_httpx(monkeypatch, client)
    prov = ResendEmailProvider(api_key="re_k", from_email="hi@x.com")

    result = await prov.send(_REQ)  # must not raise into the caller
    assert result.status == "failed"
    assert result.delivered is False


@pytest.mark.asyncio
async def test_per_request_from_overrides_default(monkeypatch):
    client = _FakeClient(resp=_FakeResp(200, {"id": "m"}))
    _patch_httpx(monkeypatch, client)
    prov = ResendEmailProvider(api_key="re_k", from_email="default@x.com")

    await prov.send(
        EmailSendRequest(to_email="a@b.com", subject="s", html="h", from_email="override@x.com")
    )
    assert client.last_call["json"]["from"] == "override@x.com"
