"""SSRF guard for outbound fetches of URLs that may be influenced by user data.

Phase 5.3/5.4 hardening. When the server itself fetches a URL (e.g. downloading
a video asset before uploading it to YouTube), a URL that points at a private /
loopback / link-local / cloud-metadata address turns that fetch into a
Server-Side Request Forgery — an attacker could probe internal services or the
`169.254.169.254` metadata endpoint.

`assert_public_url` resolves the host and refuses unless EVERY resolved address
is a public, routable IP. Fails closed. It does not (and cannot fully) defeat
DNS-rebinding TOCTOU on its own, but it blocks the overwhelmingly common vectors
and every literal-IP / obvious-hostname case.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe for the server to fetch."""


_BLOCKED_HOSTS = frozenset(
    {"localhost", "metadata.google.internal", "metadata"}
)


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local        # 169.254.0.0/16 + fe80::/10 (cloud metadata)
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def assert_public_url(url: str, *, require_https: bool = False) -> str:
    """Return `url` if it is safe to fetch, else raise UnsafeURLError.

    Rejects non-http(s) schemes, missing hosts, blocked hostnames, and any host
    that is (or resolves to) a non-public IP."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    if require_https and parsed.scheme != "https":
        raise UnsafeURLError("url must be https")

    host = (parsed.hostname or "").strip()
    if not host:
        raise UnsafeURLError("url has no host")
    if host.lower() in _BLOCKED_HOSTS:
        raise UnsafeURLError(f"host is blocked: {host}")

    # Literal IP → check directly (skips DNS).
    try:
        ipaddress.ip_address(host)
        if not _is_public_ip(host):
            raise UnsafeURLError(f"host is a non-public IP: {host}")
        return url
    except ValueError:
        pass  # not a literal IP — resolve it

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as e:
        raise UnsafeURLError(f"could not resolve host: {host}") from e

    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise UnsafeURLError(f"host did not resolve: {host}")
    for ip in resolved:
        if not _is_public_ip(ip):
            raise UnsafeURLError(f"host {host} resolves to a non-public IP: {ip}")
    return url
