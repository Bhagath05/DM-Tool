"""Verify Clerk-issued JWTs using the instance JWKS.

Clerk signs session JWTs with RS256. Public keys live at the instance's
.well-known/jwks.json endpoint. We cache them in memory and refresh on
verification failure (handles key rotation).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import structlog
from fastapi import Depends, Header, HTTPException, status
from jose import jwt
from jose.exceptions import JWTError

from aicmo.auth.clerk_profile import profile_from_claims
from aicmo.config import get_settings

settings = get_settings()
log = structlog.get_logger()

_JWKS_CACHE: dict[str, object] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: str
    session_id: str | None
    org_id: str | None
    claims: dict
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


async def _fetch_jwks(force: bool = False) -> dict:
    now = time.time()
    cached_keys = _JWKS_CACHE.get("keys")
    fetched_at = float(_JWKS_CACHE.get("fetched_at") or 0)
    if not force and cached_keys is not None and (now - fetched_at) < _JWKS_TTL_SECONDS:
        return cached_keys  # type: ignore[return-value]

    if not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_JWKS_URL is not configured",
        )

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(settings.clerk_jwks_url)
        resp.raise_for_status()
        jwks = resp.json()

    _JWKS_CACHE["keys"] = jwks
    _JWKS_CACHE["fetched_at"] = now
    return jwks


# Phase S2.7 — clock-skew tolerance for `exp` / `iat` / `nbf`.
# 30 seconds covers normal NTP drift without meaningfully extending the
# replay window. Clerk default session lifetime is ~60 minutes, so 30s
# is < 1% of the token's validity.
_JWT_LEEWAY_SECONDS = 30


def _verify_token(token: str, jwks: dict) -> dict:
    """Verify a Clerk-signed JWT.

    Hardening (Phase S2.7):
    - When CLERK_JWT_AUDIENCE is set, `aud` is verified explicitly.
      Empty (dev default) preserves the prior verify_aud=False behaviour
      so the existing dev/staging deploys keep working without churn.
    - `iss` is verified when CLERK_JWT_ISSUER is set (unchanged).
    - `exp`, `iat`, `nbf` are always verified with 30s leeway.
    - Algorithm pinned to RS256; the `alg=none` / HS256 confusion
      attacks are not possible against this code path.
    """
    audience = settings.clerk_jwt_audience or None
    return jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        audience=audience,
        issuer=settings.clerk_jwt_issuer or None,
        options={
            "verify_aud": audience is not None,
            "verify_iss": bool(settings.clerk_jwt_issuer),
            "verify_exp": True,
            "verify_iat": True,
            "verify_nbf": True,
            "require_exp": True,
            # python-jose reads leeway from options.
            "leeway": _JWT_LEEWAY_SECONDS,
        },
    )


def _clerk_configured() -> bool:
    """Treat .env.example placeholder values as 'not configured' so the
    dev-bypass triggers when the developer has only copied the template.

    Used by both `require_user` (per-request) and `assert_clerk_for_non_dev`
    (at app startup).
    """
    issuer = settings.clerk_jwt_issuer or ""
    jwks_url = settings.clerk_jwks_url or ""
    if not issuer or not jwks_url:
        return False
    placeholders = ("your-instance", "replace_me", "example.com")
    if any(p in issuer for p in placeholders):
        return False
    if any(p in jwks_url for p in placeholders):
        return False
    return True


# Stable identity returned in demo mode. Anything that depends on
# `clerk_user_id` (lazy-create, audit rows, Sentry tags) joins on this
# string. Keep it constant across restarts so prior demo data remains
# attributable to the same logical user.
DEMO_USER_CLERK_ID = "dev-user"
DEMO_USER_EMAIL = "dev-user@pending.local"


def _auth_context_from_claims(
    *,
    user_id: str,
    session_id: str | None,
    org_id: str | None,
    claims: dict,
) -> AuthContext:
    email, display_name, avatar_url = profile_from_claims(claims)
    return AuthContext(
        user_id=user_id,
        session_id=session_id,
        org_id=org_id,
        claims=claims,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
    )


def assert_auth_config_valid() -> None:
    """Hard-fail at app startup if AUTH_MODE expects Clerk but Clerk
    isn't configured. demo mode requires no Clerk config; clerk and
    hybrid modes both verify real JWTs (clerk strictly, hybrid when
    a Bearer header is present), so both require live Clerk env.

    Phase S2.6 — additionally, production must run AUTH_MODE=clerk.
    demo allows unsigned access; hybrid lets anonymous traffic resolve
    to the demo-user. Neither is acceptable for a customer-facing
    deploy.

    This is the single defence against a misconfigured deploy that
    thinks it's verifying Clerk JWTs but is actually accepting
    arbitrary tokens.
    """
    if settings.api_env == "production" and settings.auth_mode != "clerk":
        raise SystemExit(
            f"FATAL: AUTH_MODE={settings.auth_mode!r} in production. "
            "Production must run AUTH_MODE=clerk — demo accepts every "
            "request as the demo-user, and hybrid lets anonymous traffic "
            "fall through the same way. Refusing to start."
        )

    if settings.auth_mode == "demo":
        return
    # auth_mode in {"clerk", "hybrid"} — Clerk verification path exists.
    if not _clerk_configured():
        raise SystemExit(
            f"FATAL: AUTH_MODE={settings.auth_mode!r} but Clerk is not "
            "configured. Set CLERK_JWT_ISSUER and CLERK_JWKS_URL to real "
            "values (not the .env.example placeholders) before booting. "
            "Refusing to start — leaving Clerk un-enforced in this mode "
            "would silently accept unsigned tokens as authenticated."
        )


# Kept as a thin alias for back-compat with any external code that may
# still import the old name. New callers should use assert_auth_config_valid.
assert_clerk_for_non_dev = assert_auth_config_valid


async def require_user(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    # Demo mode short-circuits all auth machinery and returns a stable
    # dev-user. Used for the public-demo product flow where the landing
    # page → /dashboard works without sign-in.
    if settings.auth_mode == "demo":
        return _auth_context_from_claims(
            user_id=DEMO_USER_CLERK_ID,
            session_id=None,
            org_id=None,
            claims={"sub": DEMO_USER_CLERK_ID, "auth_mode": "demo", "email": DEMO_USER_EMAIL},
        )

    # Hybrid mode: when no Bearer token is sent we still serve the
    # demo-user (so anonymous /dashboard works), but a present Bearer
    # falls through to the Clerk verification path below.
    if settings.auth_mode == "hybrid" and (
        not authorization or not authorization.lower().startswith("bearer ")
    ):
        return _auth_context_from_claims(
            user_id=DEMO_USER_CLERK_ID,
            session_id=None,
            org_id=None,
            claims={
                "sub": DEMO_USER_CLERK_ID,
                "auth_mode": "hybrid-anonymous",
                "email": DEMO_USER_EMAIL,
            },
        )

    # auth_mode in {"clerk", "hybrid-with-token"} — real JWT verification.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()

    jwks = await _fetch_jwks()
    try:
        claims = _verify_token(token, jwks)
    except JWTError:
        jwks = await _fetch_jwks(force=True)
        try:
            claims = _verify_token(token, jwks)
        except JWTError as e:
            # Surface WHY the token was rejected so a misconfigured Clerk deploy
            # is debuggable from the logs (the reason is "Invalid audience",
            # "Invalid issuer", "Signature verification failed", "expired", …).
            # The token itself is never logged.
            log.warning(
                "auth.token_rejected",
                reason=str(e),
                issuer_configured=bool(settings.clerk_jwt_issuer),
                audience_configured=bool(settings.clerk_jwt_audience),
                jwks_url_configured=bool(settings.clerk_jwks_url),
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e

    return _auth_context_from_claims(
        user_id=str(claims.get("sub", "")),
        session_id=claims.get("sid"),
        org_id=claims.get("org_id"),
        claims=claims,
    )


CurrentUser = Depends(require_user)
