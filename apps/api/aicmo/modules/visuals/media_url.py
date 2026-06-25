"""HMAC-signed media URL helpers.

A signed URL has the shape:
    /api/v1/media/{rendered_id}?exp=<unix>&sig=<hex>

`sig = HMAC_SHA256(secret, f"{rendered_id}:{exp}")` truncated to 32 chars.
Default expiry is 30 days — short enough that leaked URLs don't live
forever, long enough that founders can re-share without re-rendering.

We rely on the path component for the resource id (not the query) so
caches/CDNs key on it naturally if/when we add a CDN.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from aicmo.config import get_settings

_DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _signing_key() -> bytes:
    settings = get_settings()
    secret = settings.media_signing_secret or settings.clerk_secret_key
    if not secret:
        # Dev fallback so the system runs without explicit config. NOT
        # safe for production — but neither is dev mode in general.
        secret = "aicmo-dev-media-signing-key"
    return secret.encode("utf-8")


def _sign(rendered_id: uuid.UUID | str, exp: int) -> str:
    msg = f"{rendered_id}:{exp}".encode("utf-8")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()[:32]


def make_signed_url(
    rendered_id: uuid.UUID, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS
) -> str:
    """Build the public-facing URL the frontend embeds in <img>."""
    exp = int(time.time()) + ttl_seconds
    sig = _sign(rendered_id, exp)
    settings = get_settings()
    # Prefer the configured public base URL so emails/embeds work outside dev.
    base = settings.public_base_url.rstrip("/")
    # public_base_url is the WEB origin (e.g. localhost:3000). The web's
    # API_URL env var points the frontend at the actual API host. For
    # signed media we want the API host directly so curl/img-src works.
    # Strip any obvious "/3000" tail to derive the API host conservatively.
    # In practice the frontend resolves API_URL itself; for the signed link
    # we just emit a relative path and let the frontend prepend NEXT_PUBLIC_API_URL.
    return f"/api/v1/media/{rendered_id}?exp={exp}&sig={sig}"


def verify_signed_url(
    rendered_id: uuid.UUID, exp: int, sig: str
) -> tuple[bool, str | None]:
    """Returns (ok, reason_if_not_ok)."""
    if exp < int(time.time()):
        return False, "expired"
    expected = _sign(rendered_id, exp)
    if not hmac.compare_digest(expected, sig):
        return False, "signature mismatch"
    return True, None
