"""Phase 5.3 — SSRF guard for server-side URL fetches."""

from __future__ import annotations

import pytest

from aicmo.security.ssrf import UnsafeURLError, assert_public_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",            # loopback
        "http://10.0.0.5/x",             # private (RFC1918)
        "http://192.168.1.1/x",          # private
        "http://172.16.5.5/x",           # private
        "http://169.254.169.254/latest", # cloud metadata (link-local)
        "http://0.0.0.0/x",              # unspecified
        "https://[::1]/x",               # ipv6 loopback
        "http://localhost/x",            # blocked hostname
        "http://metadata.google.internal/x",  # blocked hostname
    ],
)
async def test_blocks_internal_and_metadata_targets(url):
    with pytest.raises(UnsafeURLError):
        await assert_public_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://x/"])
async def test_blocks_dangerous_schemes(url):
    with pytest.raises(UnsafeURLError):
        await assert_public_url(url)


@pytest.mark.asyncio
async def test_allows_public_ip_literal():
    # Public literal IPs (no DNS) pass — legitimate CDN/storage URLs resolve here.
    assert await assert_public_url("http://8.8.8.8/video.mp4") == "http://8.8.8.8/video.mp4"


@pytest.mark.asyncio
async def test_require_https_flag():
    with pytest.raises(UnsafeURLError):
        await assert_public_url("http://8.8.8.8/x", require_https=True)
    assert await assert_public_url("https://8.8.8.8/x", require_https=True)


@pytest.mark.asyncio
async def test_resolved_private_host_blocked(monkeypatch):
    # A hostname that RESOLVES to a private IP is blocked (DNS-rebinding vector).
    async def fake_getaddrinfo(host, port, **kw):
        return [(2, 1, 6, "", ("10.1.2.3", port))]

    import aicmo.security.ssrf as ssrf

    class _Loop:
        getaddrinfo = staticmethod(fake_getaddrinfo)

    monkeypatch.setattr(ssrf.asyncio, "get_event_loop", lambda: _Loop())
    with pytest.raises(UnsafeURLError):
        await assert_public_url("https://evil.example.com/x")
