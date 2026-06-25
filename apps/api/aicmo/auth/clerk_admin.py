"""Phase 10.2c — Thin admin-API client for Clerk.

Single responsibility: revoke a Clerk session by id. We don't try to
abstract every Clerk admin operation behind a god-client — each
phase adds the calls it needs.

Behaviour matrix:

  CLERK_SECRET_KEY set    → real HTTPS call to api.clerk.com
  CLERK_SECRET_KEY empty  → no-op, returns LOCAL_ONLY sentinel
  HTTP error              → REMOTE_FAILED sentinel (caller still marks
                            our local row revoked so the founder isn't
                            left thinking nothing happened)

The 'local-only' path exists so dev environments (no real Clerk
configured) still get a working settings page — the row turns
revoked, the audit event fires, the UI updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx
import structlog

from aicmo.config import get_settings

log = structlog.get_logger()

# Outcomes are strings (not an Enum) to match the column type in the
# `user_session` table and the Pydantic Literal in schemas.py.
RevocationOutcome = Literal["remote_ok", "local_only", "remote_failed"]


@dataclass(frozen=True, slots=True)
class RevocationResult:
    outcome: RevocationOutcome
    detail: str  # human-readable, surfaced in audit metadata


async def revoke_session(clerk_session_id: str) -> RevocationResult:
    """Revoke a Clerk session. Never raises — returns a RevocationResult.

    Why no-raise: the caller (security service) needs to mark our local
    row revoked regardless of remote outcome. Bubbling an exception
    would force the caller to wrap every call in try/except, which is
    boilerplate that hides intent. Sentinel returns are clearer.
    """
    settings = get_settings()
    secret = settings.clerk_secret_key.strip()

    if not secret:
        log.info(
            "clerk_admin.revoke.local_only",
            session_id=clerk_session_id,
            reason="no_secret",
        )
        return RevocationResult(
            outcome="local_only",
            detail="CLERK_SECRET_KEY not configured; local revoke only.",
        )

    url = f"https://api.clerk.com/v1/sessions/{clerk_session_id}/revoke"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                },
            )
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.warning(
            "clerk_admin.revoke.transport_error",
            session_id=clerk_session_id,
            error=str(exc),
        )
        return RevocationResult(
            outcome="remote_failed",
            detail=f"transport_error: {type(exc).__name__}",
        )

    if 200 <= resp.status_code < 300:
        return RevocationResult(
            outcome="remote_ok",
            detail=f"clerk_status={resp.status_code}",
        )

    # Clerk returns 404 if the session is already revoked / expired.
    # Treat 404 as a successful no-op — the session is no longer
    # usable, which is the outcome the founder asked for.
    if resp.status_code == 404:
        return RevocationResult(
            outcome="remote_ok",
            detail="clerk_404_already_gone",
        )

    log.warning(
        "clerk_admin.revoke.http_error",
        session_id=clerk_session_id,
        status=resp.status_code,
        body=resp.text[:200],
    )
    return RevocationResult(
        outcome="remote_failed",
        detail=f"clerk_status={resp.status_code}",
    )
