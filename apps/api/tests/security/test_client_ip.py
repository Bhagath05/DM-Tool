"""Phase 5.1/5.9 — X-Forwarded-For client-IP extraction (anti-spoofing)."""

from __future__ import annotations

from types import SimpleNamespace

from aicmo.middleware import rate_limit


def _request(*, xff=None, peer="9.9.9.9"):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=peer),
        url=SimpleNamespace(path="/api/v1/x"),
    )


def _patch_env(monkeypatch, env, hops=1):
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: SimpleNamespace(api_env=env, trusted_proxy_hops=hops),
    )


def test_spoofed_leftmost_xff_is_ignored(monkeypatch):
    # Client sends a fake leftmost entry; the real client IP is the rightmost
    # one our trusted proxy appended.
    _patch_env(monkeypatch, "staging", hops=1)
    ip = rate_limit._client_ip(_request(xff="1.2.3.4, 5.6.7.8"))
    assert ip == "5.6.7.8"  # NOT the spoofable "1.2.3.4"


def test_single_xff_entry(monkeypatch):
    _patch_env(monkeypatch, "production", hops=1)
    assert rate_limit._client_ip(_request(xff="5.6.7.8")) == "5.6.7.8"


def test_two_trusted_hops(monkeypatch):
    _patch_env(monkeypatch, "production", hops=2)
    # e.g. CDN + Render: real client is 2 from the right.
    assert rate_limit._client_ip(_request(xff="1.1.1.1, 2.2.2.2, 3.3.3.3")) == "2.2.2.2"


def test_development_ignores_xff_uses_peer(monkeypatch):
    _patch_env(monkeypatch, "development", hops=1)
    # In dev there's no trusted proxy → never trust the header.
    assert rate_limit._client_ip(_request(xff="1.2.3.4", peer="7.7.7.7")) == "7.7.7.7"


def test_shorter_chain_than_hops_falls_back(monkeypatch):
    _patch_env(monkeypatch, "production", hops=3)
    # Fewer entries than configured hops → fall back to leftmost (best effort).
    assert rate_limit._client_ip(_request(xff="5.6.7.8")) == "5.6.7.8"
