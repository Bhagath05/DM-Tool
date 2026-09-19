"""Phase 10.2c — Security service layer.

Six public operations:

  record_event(...)             — append-only audit insert
  mark_session_revoked()        — revoke one session locally; emits event
  revoke_all_sessions()         — revoke every other session; emits event
  list_sessions()               — own-user inventory, current-flagged
  list_events()                 — paginated own-user timeline
  build_summary()               — Security page hero stats

Boundary rules (enforced by tests):

  - `record_event` is the ONLY function that writes to security_event.
    Every other surface goes through it so we can centralise PII
    scrubbing if we ever add it.
  - User-id scoping is always passed explicitly — no "ambient user"
    fallback. Cross-user leaks are prevented at the call site, not
    the SQL level.

The session inventory (list/revoke/revoke-all) reads the authoritative
first-party session store (`aicmo.auth.models.UserSession` → `user_sessions`).
The current session is spared from the per-id revoke (use sign-out, which
revokes it through `aicmo.auth.sessions`). The `security_event` audit table
is this module's own; its `clerk_session_id` column is a legacy name now
reused to reference a first-party session id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# The Active Sessions feature reads the authoritative first-party session store
# (`aicmo.auth.models.UserSession` → `user_sessions`), not the legacy Clerk
# mirror. `SecurityEvent` remains this module's own audit table.
from aicmo.auth.models import UserSession
from aicmo.modules.security.models import SecurityEvent
from aicmo.modules.security.schemas import (
    RevokeAllResponse,
    RevokeSessionResponse,
    SecurityEventCreate,
    SecurityEventList,
    SecurityEventRead,
    SecurityEventType,
    SecuritySummary,
    SessionList,
    SessionRead,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------


# Events the internal POST /security/events endpoint will accept.
# Everything else MUST arrive via the Clerk webhook — accepting them
# from the client would let a logged-in user forge "password_change"
# entries in their own timeline.
ALLOWED_CLIENT_EVENTS: frozenset[SecurityEventType] = frozenset({"failed_login", "mfa_challenge"})

# Heuristic threshold for the `suspicious_signal` boolean on the
# Security summary card.
SUSPICIOUS_FAILED_LOGINS_24H = 3


# ---------------------------------------------------------------------
#  Exceptions
# ---------------------------------------------------------------------


class SessionNotFound(Exception):
    """The session id doesn't exist, or belongs to a different user."""


class CurrentSessionRevokeRefused(Exception):
    """A user tried to revoke their own current session via the per-id
    endpoint. They must use a sign-out flow instead — otherwise the
    revoke would race against the page's own next request and surface
    as a confusing 401 mid-action."""


class EventTypeNotAllowedFromClient(Exception):
    """The client tried to POST an event type that only the webhook
    can produce (e.g. `login`). Returned as 403."""

    def __init__(self, event_type: str) -> None:
        super().__init__(event_type)
        self.event_type = event_type


# ---------------------------------------------------------------------
#  Recording — the single write path
# ---------------------------------------------------------------------


async def record_event(
    session: AsyncSession,
    *,
    event_type: SecurityEventType,
    user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None = None,
    clerk_session_id: str | None = None,
    actor: str = "self",
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> SecurityEvent:
    """Append a row to security_event. The ONLY function that writes
    there — every other path must call this, never INSERT directly.
    """
    row = SecurityEvent(
        user_id=user_id,
        organization_id=organization_id,
        clerk_session_id=clerk_session_id,
        event_type=event_type,
        actor=actor,
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=metadata or {},
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------
#  Session inventory
# ---------------------------------------------------------------------


async def list_sessions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_session_id: str | None,
    include_revoked: bool = False,
    limit: int = 50,
) -> SessionList:
    """List the user's first-party sessions, newest-first. Expired sessions are
    excluded from the active list; the caller's current session is flagged."""
    now = datetime.now(UTC)
    stmt = select(UserSession).where(UserSession.user_id == user_id)
    if not include_revoked:
        stmt = stmt.where(
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    stmt = stmt.order_by(desc(UserSession.last_used_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return SessionList(sessions=[_to_session_read(r, current_session_id, now) for r in rows])


async def mark_session_revoked(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_row_id: uuid.UUID,
    current_session_id: str | None,
    actor: str = "self",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> RevokeSessionResponse:
    """Revoke ONE first-party session row.

    1. Load + ownership check (404 vs cross-user leak)
    2. Refuse if it's the caller's current session (they must use sign-out —
       revoking your own live session mid-request would 401 the page)
    3. Set revoked_at; emit a `session_revoke` audit event
    """
    row = await session.get(UserSession, session_row_id)
    if row is None or row.user_id != user_id:
        raise SessionNotFound()
    if row.revoked_at is not None:
        # Idempotent — already revoked. Return current state.
        return RevokeSessionResponse(
            session=_to_session_read(row, current_session_id, datetime.now(UTC)),
        )

    if current_session_id is not None and str(row.id) == current_session_id:
        raise CurrentSessionRevokeRefused()

    now = datetime.now(UTC)
    row.revoked_at = now
    await session.flush()

    await record_event(
        session,
        event_type="session_revoke",
        user_id=user_id,
        clerk_session_id=str(row.id),
        actor=actor,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"revoked_session_id": str(row.id)},
    )

    return RevokeSessionResponse(
        session=_to_session_read(row, current_session_id, now),
    )


async def revoke_all_sessions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_session_id: str | None,
    actor: str = "self",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> RevokeAllResponse:
    """Revoke every active first-party session for the user EXCEPT the current
    one ("sign out everywhere else"). Each revocation emits its own audit event;
    the spared current session is reported back."""
    stmt = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    rows = (await session.execute(stmt)).scalars().all()

    revoked_count = 0
    skipped_current = False
    for row in rows:
        if current_session_id is not None and str(row.id) == current_session_id:
            skipped_current = True
            continue
        await mark_session_revoked(
            session,
            user_id=user_id,
            session_row_id=row.id,
            current_session_id=current_session_id,
            actor=actor,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        revoked_count += 1

    return RevokeAllResponse(
        revoked_count=revoked_count,
        skipped_current=skipped_current,
    )


# ---------------------------------------------------------------------
#  Event timeline
# ---------------------------------------------------------------------


async def list_events(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 50,
    before: datetime | None = None,
) -> SecurityEventList:
    """Cursor-paginated own-user event timeline (newest first).

    `before` is the cursor — pass the `occurred_at` of the last row from
    the previous page. We over-fetch by one to compute `has_more`
    without an extra COUNT.
    """
    stmt = select(SecurityEvent).where(SecurityEvent.user_id == user_id)
    if before is not None:
        stmt = stmt.where(SecurityEvent.occurred_at < before)
    stmt = stmt.order_by(desc(SecurityEvent.occurred_at)).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return SecurityEventList(
        events=[_to_event_read(r) for r in page],
        has_more=has_more,
    )


async def record_client_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payload: SecurityEventCreate,
    ip_address: str | None,
    user_agent: str | None,
) -> SecurityEventRead:
    """POST /security/events handler — gated allowlist.

    Clients can witness `failed_login` (the 401 they just got) and
    `mfa_challenge` (the form they just submitted). Anything else
    bounces with EventTypeNotAllowedFromClient → 403.
    """
    if payload.event_type not in ALLOWED_CLIENT_EVENTS:
        raise EventTypeNotAllowedFromClient(payload.event_type)
    row = await record_event(
        session,
        event_type=payload.event_type,
        user_id=user_id,
        clerk_session_id=payload.clerk_session_id,
        actor="self",
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=payload.metadata,
    )
    return _to_event_read(row)


# ---------------------------------------------------------------------
#  Summary
# ---------------------------------------------------------------------


async def build_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> SecuritySummary:
    """Compute the Security page hero card."""
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)

    # Active session count.
    active_count_stmt = select(func.count(UserSession.id)).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    active_count = (await session.execute(active_count_stmt)).scalar_one()

    # Last successful login.
    last_login_stmt = (
        select(SecurityEvent)
        .where(
            SecurityEvent.user_id == user_id,
            SecurityEvent.event_type == "login",
        )
        .order_by(desc(SecurityEvent.occurred_at))
        .limit(1)
    )
    last_login = (await session.execute(last_login_stmt)).scalar_one_or_none()

    # 24h event counts.
    recent_event_count_stmt = select(func.count(SecurityEvent.id)).where(
        SecurityEvent.user_id == user_id,
        SecurityEvent.occurred_at >= day_ago,
    )
    recent_event_count = (await session.execute(recent_event_count_stmt)).scalar_one()

    recent_failed_stmt = select(func.count(SecurityEvent.id)).where(
        SecurityEvent.user_id == user_id,
        SecurityEvent.event_type == "failed_login",
        SecurityEvent.occurred_at >= day_ago,
    )
    recent_failed = (await session.execute(recent_failed_stmt)).scalar_one()

    # Suspicious-signal heuristic.
    suspicious = bool(
        recent_failed >= SUSPICIOUS_FAILED_LOGINS_24H
        or _is_new_country_login(last_login, session_user_id=user_id)
    )

    return SecuritySummary(
        active_session_count=int(active_count),
        last_login_at=last_login.occurred_at if last_login else None,
        last_login_ip=str(last_login.ip_address) if last_login and last_login.ip_address else None,
        last_login_country=(
            last_login.event_metadata.get("geo_country")
            if last_login and last_login.event_metadata
            else None
        ),
        recent_event_count_24h=int(recent_event_count),
        recent_failed_login_count_24h=int(recent_failed),
        suspicious_signal=suspicious,
    )


def _is_new_country_login(last_login: SecurityEvent | None, *, session_user_id: uuid.UUID) -> bool:
    """Cheap heuristic: the last login carries a `new_country=true` flag
    in metadata if the dispatcher decided this was the first time we'd
    seen this country for the user. Phase 10.2c doesn't ship that
    detection (Clerk doesn't give us a clean signal yet) — this stub
    returns False but the column is plumbed so a future enhancement
    doesn't need a schema change."""
    if last_login is None:
        return False
    return bool(last_login.event_metadata.get("new_country"))


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


def _to_session_read(
    row: UserSession,
    current_session_id: str | None,
    now: datetime,
) -> SessionRead:
    is_active = row.revoked_at is None and (row.expires_at is None or row.expires_at > now)
    return SessionRead(
        id=row.id,
        user_agent=row.user_agent,
        ip=row.ip,
        last_seen_at=row.last_used_at or row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        is_current=(current_session_id is not None and str(row.id) == current_session_id),
        is_active=is_active,
        created_at=row.created_at,
    )


def _to_event_read(row: SecurityEvent) -> SecurityEventRead:
    return SecurityEventRead(
        id=row.id,
        event_type=row.event_type,  # type: ignore[arg-type]
        actor=row.actor,  # type: ignore[arg-type]
        clerk_session_id=row.clerk_session_id,
        ip_address=str(row.ip_address) if row.ip_address else None,
        user_agent=row.user_agent,
        metadata=row.event_metadata or {},
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )
