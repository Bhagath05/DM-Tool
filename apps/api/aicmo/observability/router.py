"""Observability verification endpoints.

Mounted at /api/v1/debug — but ONLY when api_env != "production".
The production check happens in main.py at route registration so the
debug routes simply don't exist in prod, eliminating any risk of an
attacker calling them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.config import get_settings

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/sentry")
async def sentry_test_unauthed() -> dict[str, str]:
    """Force an unhandled exception so we can verify Sentry capture.

    Hit `GET /api/v1/debug/sentry` from dev/staging. The exception
    will surface in Sentry within ~1s with environment=staging|development
    and api_version tags.
    """
    raise RuntimeError("Sentry verification (unauthenticated path)")


@router.get("/sentry-authed")
async def sentry_test_authed(
    auth: AuthContext = Depends(require_user),
) -> dict[str, str]:
    """Same as /sentry but raises AFTER auth so tenant tagging — when
    paired with tenant headers — gets attached. Use this to verify
    user.id + organization_id + brand_id show up in the captured event.
    """
    raise RuntimeError(
        f"Sentry verification (authed as clerk_user_id={auth.user_id})"
    )


@router.get("/sentry-config")
async def sentry_config_inspect() -> dict[str, object]:
    """Read-only: what config did Sentry init with? Useful for ops to
    confirm a deploy picked up the right DSN / environment / release
    without exposing the DSN itself."""
    s = get_settings()
    return {
        "sentry_dsn_configured": bool(s.sentry_dsn),
        "sentry_dsn_prefix": s.sentry_dsn[:32] + "..." if s.sentry_dsn else None,
        "environment": s.sentry_environment or s.api_env,
        "api_env": s.api_env,
        "api_version": s.api_version,
        "traces_sample_rate": s.sentry_traces_sample_rate,
        "profiles_sample_rate": s.sentry_profiles_sample_rate,
    }


def assert_not_production() -> None:
    """Guard for the router include. Called from main.py — raises so
    the debug endpoints never exist in production."""
    s = get_settings()
    if s.api_env == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="debug endpoints disabled in production",
        )
