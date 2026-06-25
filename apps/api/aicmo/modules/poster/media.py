"""HMAC-signed serving for rendered poster PNGs.

A poster lives in the storage backend under an opaque key. We hand the
frontend a signed, expiring URL (`/api/v1/poster/media?k=&exp=&sig=`) so the
image is viewable without auth headers (needed for <img src> and for the
LinkedIn publish step) yet can't be enumerated.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from aicmo.config import get_settings

_DEFAULT_TTL = 7 * 24 * 3600  # a week — covers preview + publish


def _secret() -> bytes:
    s = get_settings()
    raw = (
        getattr(s, "media_signing_secret", "")
        or getattr(s, "clerk_secret_key", "")
        or "poster-dev-secret"
    )
    return raw.encode()


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def _unb64(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


def _sig(kb: str, exp: int) -> str:
    return hmac.new(_secret(), f"{kb}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def sign_storage_key(key: str, *, ttl: int = _DEFAULT_TTL) -> str:
    exp = int(time.time()) + ttl
    kb = _b64(key)
    return f"/api/v1/poster/media?k={kb}&exp={exp}&sig={_sig(kb, exp)}"


def verify(k: str, exp: int, sig: str) -> str | None:
    """Return the storage key if the signature is valid and unexpired, else None."""
    if exp < int(time.time()):
        return None
    if not hmac.compare_digest(_sig(k, exp), sig):
        return None
    try:
        return _unb64(k)
    except Exception:  # noqa: BLE001
        return None
