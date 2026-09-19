"""Cookie wiring for first-party sessions.

Two cookies, deliberately different:

  * session cookie  — HttpOnly (JS can never read it), Secure, SameSite from
    config. Holds the raw session token. This is the credential.
  * CSRF cookie      — NOT HttpOnly (the SPA reads it and echoes it back in a
    header for the double-submit check), Secure, SameSite. Holds a random,
    non-secret value; its only job is to prove the request came from our own
    page, not a cross-site form.

All flags come from Settings so a same-site local deploy and a cross-site
prod split are both expressible without code changes.
"""

from __future__ import annotations

from fastapi import Response

from aicmo.config import Settings


def set_session_cookie(response: Response, *, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain or None,
        path="/",
    )


def clear_session_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain or None,
        path="/",
    )


def set_csrf_cookie(response: Response, *, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=False,  # readable by the SPA for the double-submit header
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain or None,
        path="/",
    )


def clear_csrf_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        domain=settings.session_cookie_domain or None,
        path="/",
    )
