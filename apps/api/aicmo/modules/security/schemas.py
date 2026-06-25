"""Phase 10.2c — Pydantic schemas for sessions + security events.

Hard rule (mirrored from integrations + notifications): no schema in
this module exposes secrets, tokens, passwords, MFA codes, or recovery
codes. Reflection guard in tests/security/test_schemas.py enforces.

IP addresses ARE exposed — they're the founder's own data and the whole
point of the security page is to show "you signed in from this IP."
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------
#  Enums — kept in lock-step with migration 0024 CHECK constraints
# ---------------------------------------------------------------------

SecurityEventType = Literal[
    "login",
    "logout",
    "failed_login",
    "password_change",
    "mfa_challenge",
    "session_revoke",
]

Actor = Literal["self", "admin", "system", "unknown"]

RevokedBy = Literal["user", "admin", "webhook", "system"]

RevocationStatus = Literal["remote_ok", "local_only", "remote_failed"]
# remote_ok    — Clerk admin API acknowledged the revoke
# local_only   — Clerk call skipped (no CLERK_SECRET_KEY in env)
# remote_failed — Clerk call returned non-2xx; row still marked revoked locally


# ---------------------------------------------------------------------
#  Session inventory
# ---------------------------------------------------------------------


class SessionRead(BaseModel):
    """One row in the Settings → Security → Devices list.

    `is_current` is computed server-side from the request's session id
    so the UI can pin the current device to the top + disable the
    "revoke" button on it (revoking your own current session would log
    you out instantly with no confirmation grace period).
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    clerk_session_id: str
    user_agent: str | None
    ip_address: str | None
    geo_country: str | None
    geo_city: str | None
    last_seen_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoked_by: RevokedBy | None
    revocation_status: RevocationStatus | None
    is_current: bool = Field(
        description="True if this row matches the requester's current session.",
    )
    is_active: bool = Field(
        description="Convenience: revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now).",
    )
    created_at: datetime


class SessionList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessions: list[SessionRead]


class RevokeSessionResponse(BaseModel):
    """Return value from POST /sessions/{id}/revoke.

    Tells the caller whether Clerk-side revocation actually landed
    (vs. local-only) — important UX so the page can warn the founder
    if their secret key isn't configured in dev.
    """

    model_config = ConfigDict(extra="forbid")
    session: SessionRead
    revocation_status: RevocationStatus


class RevokeAllResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revoked_count: int
    skipped_current: bool = Field(
        description="True if a current session existed and was deliberately spared.",
    )


# ---------------------------------------------------------------------
#  Security events
# ---------------------------------------------------------------------


class SecurityEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    event_type: SecurityEventType
    actor: Actor
    clerk_session_id: str | None
    ip_address: str | None
    user_agent: str | None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Event-specific extras (mfa method, fail reason, etc.). "
            "Server enforces no secrets land here."
        ),
    )
    occurred_at: datetime
    created_at: datetime


class SecurityEventList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[SecurityEventRead]
    has_more: bool = Field(
        description="True if more events exist beyond the returned page.",
    )


class SecurityEventCreate(BaseModel):
    """Body for the internal recorder endpoint POST /security/events.

    Only event types the frontend can legitimately witness are allowed:
    `mfa_challenge` (rendered the MFA UI), `failed_login` (saw the
    server's 401). The other four types come from the Clerk webhook
    exclusively — clients trying to POST them are rejected (see
    ALLOWED_CLIENT_EVENTS in service.py).
    """

    model_config = ConfigDict(extra="forbid")
    event_type: SecurityEventType
    clerk_session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=32)


# ---------------------------------------------------------------------
#  Security summary (Settings → Security page hero)
# ---------------------------------------------------------------------


class SecuritySummary(BaseModel):
    """Top-of-page stats for the Security settings card."""

    model_config = ConfigDict(extra="forbid")

    active_session_count: int
    last_login_at: datetime | None
    last_login_ip: str | None
    last_login_country: str | None
    recent_event_count_24h: int = Field(
        description="Events in the last 24h — surfaced as a 'recent activity' badge.",
    )
    recent_failed_login_count_24h: int = Field(
        description="Failed logins in last 24h. Non-zero → surface a warning chip.",
    )
    suspicious_signal: bool = Field(
        description=(
            "Heuristic: >=3 failed logins in 24h, OR new-country login in "
            "last 24h. Drives the 'something unusual happened' banner."
        ),
    )


# ---------------------------------------------------------------------
#  Webhook payloads (Clerk → us)
# ---------------------------------------------------------------------
# These are NOT exposed via the OpenAPI schema (the webhook endpoint
# uses a Request directly). They're here as type aids for the dispatcher.


ClerkEventType = Literal[
    "session.created",
    "session.ended",
    "session.removed",
    "session.revoked",
    "user.updated",
    "user.created",
    "user.deleted",
]
