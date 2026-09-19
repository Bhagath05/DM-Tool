"""Phase 13 — YouTube OAuth methods (mocked HTTP, no live credentials).

Verifies the authorization URL shape (incl. the offline/consent params needed
to receive a refresh token), the code→token exchange, the refresh flow
(reusing the stored refresh token when the provider omits a new one), and that
a token-exchange failure surfaces rather than being swallowed. No real Google
credentials — deterministic mocked responses only.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from aicmo.modules.integrations.providers.youtube import YouTubeProvider


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]


class _Client:
    def __init__(self, post_handler):
        self._post = post_handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data=None, headers=None):
        return self._post(url, data or {})


def _provider(cid="cid-123", secret="sec-xyz") -> YouTubeProvider:
    p = YouTubeProvider()
    p._client_id = cid
    p._client_secret = secret
    return p


def _patch_post(monkeypatch, handler):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client(handler))


@pytest.mark.asyncio
async def test_authorize_url_has_required_oauth_params():
    url = await _provider().authorize_url(state="STATE123", redirect_uri="https://app/cb")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert q["client_id"] == ["cid-123"]
    assert q["redirect_uri"] == ["https://app/cb"]
    assert q["state"] == ["STATE123"]  # CSRF state echoed back on the callback
    assert q["response_type"] == ["code"]
    assert q["access_type"] == ["offline"]  # required to receive a refresh token
    assert q["prompt"] == ["consent"]
    assert "youtube.readonly" in q["scope"][0]


@pytest.mark.asyncio
async def test_exchange_code_returns_tokens(monkeypatch):
    captured: dict = {}

    def handler(url, data):
        captured["url"] = url
        captured["data"] = data
        return _Resp(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    _patch_post(monkeypatch, handler)
    tokens = await _provider().exchange_code("CODE", "https://app/cb")
    assert tokens.access_token == "AT"
    assert tokens.refresh_token == "RT"
    assert tokens.expires_at is not None
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "CODE"


@pytest.mark.asyncio
async def test_refresh_reuses_stored_token_when_provider_omits_new_one(monkeypatch):
    def handler(url, data):
        assert data["grant_type"] == "refresh_token"
        return _Resp(200, {"access_token": "AT2", "expires_in": 3600})  # no new refresh_token

    _patch_post(monkeypatch, handler)
    tokens = await _provider().refresh("OLD_RT")
    assert tokens.access_token == "AT2"
    assert tokens.refresh_token == "OLD_RT"  # reused, not dropped


@pytest.mark.asyncio
async def test_exchange_code_failure_surfaces(monkeypatch):
    _patch_post(monkeypatch, lambda url, data: _Resp(400, {"error": "invalid_grant"}))
    with pytest.raises(httpx.HTTPStatusError):
        await _provider().exchange_code("BAD", "https://app/cb")
