"""Cloudflare Turnstile token verification.

Why Turnstile over hCaptcha / reCAPTCHA:
- Free at any scale, no per-call billing.
- Privacy-clean (no third-party cookies, EU-friendly).
- Faster widget, better mobile UX.
- Same verification API shape — swap is one-file change.

Dev bypass: when TURNSTILE_SECRET_KEY is empty or contains a placeholder,
verification short-circuits to success. Mirrors the Clerk pattern.
"""

from __future__ import annotations

import httpx
import structlog
from fastapi import HTTPException, status

from aicmo.config import get_settings

log = structlog.get_logger()

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_PLACEHOLDERS = ("replace_me", "your-instance", "")


def _configured() -> bool:
    secret = get_settings().turnstile_secret_key or ""
    if not secret:
        return False
    return not any(p in secret for p in _PLACEHOLDERS if p)


async def verify(token: str | None, *, remote_ip_hash: str | None = None) -> None:
    """Raise HTTPException(400) if the captcha token is invalid.

    No-ops in development if Turnstile isn't configured — keeps local
    iteration fast without forcing a Cloudflare account.
    """
    if not _configured():
        return  # dev bypass

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing captcha token",
        )

    settings = get_settings()
    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip_hash:
        # Turnstile doesn't require IP but accepts a hint for adaptive scoring.
        payload["remoteip"] = remote_ip_hash

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
            body = resp.json()
    except Exception as e:  # noqa: BLE001 — never let captcha errors crash the request
        log.warning("captcha.verify_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Captcha verifier unavailable. Try again in a moment.",
        ) from e

    if not body.get("success"):
        log.info(
            "captcha.rejected",
            error_codes=body.get("error-codes"),
            cdata=body.get("cdata"),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Captcha failed. Refresh and try again.",
        )
