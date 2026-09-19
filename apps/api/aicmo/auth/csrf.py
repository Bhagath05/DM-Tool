"""CSRF protection for cookie-authenticated, state-changing requests.

Double-submit: on login/signup we set a non-HttpOnly CSRF cookie with a random
value. The SPA reads it and echoes it in the `X-CSRF-Token` header on every
mutating request. The server requires header == cookie (constant-time). A
cross-site attacker can neither read our cookie nor set our custom header (the
latter is blocked by the CORS preflight), so a match proves the request came
from our own origin.

Belt-and-suspenders: we also reject a mutating request whose Origin (or
Referer host) is present but not in the allowlist, which stops the rare
attacker who can influence cookies but not headers.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from aicmo.auth.tokens import constant_time_equals, generate_token
from aicmo.config import Settings

# Only these methods mutate; GET/HEAD/OPTIONS are exempt (they must be safe).
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def generate_csrf_token() -> str:
    return generate_token(16)


def _origin_allowed(request: Request, settings: Settings) -> bool:
    """True if the request carries no Origin/Referer (non-browser client) or
    one that is in the CORS allowlist. A present-but-foreign origin fails."""
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if not referer:
            return True  # no browser-context header to check
        parsed = urlparse(referer)
        origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed = set(settings.cors_origins_list)
    if origin in allowed:
        return True
    regex = settings.cors_origin_regex
    if regex:
        import re

        return re.match(regex, origin) is not None
    return False


def is_origin_allowed(request: Request, settings: Settings) -> bool:
    """Public wrapper: True if the request's Origin/Referer is absent or in the
    allowlist. Used to guard cookieless auth POSTs (signup/signin/reset), which
    have no CSRF cookie yet, against cross-site submission (login CSRF)."""
    return _origin_allowed(request, settings)


def is_csrf_valid(request: Request, settings: Settings) -> bool:
    """Validate CSRF for a request. Safe methods always pass."""
    if request.method in _SAFE_METHODS:
        return True
    if not _origin_allowed(request, settings):
        return False
    cookie_val = request.cookies.get(settings.csrf_cookie_name)
    header_val = request.headers.get(settings.csrf_header_name)
    if not cookie_val or not header_val:
        return False
    return constant_time_equals(cookie_val, header_val)
