"""Phase 10.2c — Security service layer.

Six public operations:

  record_event(...)             — append-only audit insert
  register_or_touch_session()   — webhook-driven session upsert
  mark_session_revoked()        — local + Clerk-side revoke; emits event
  list_sessions()               — own-user inventory, current-flagged
  list_events()                 — paginated own-user timeline
  build_summary()               — Security page hero stats
  dispatch_webhook()            — Clerk event router (session.* + user.*)

Boundary rules (enforced by tests):

  - `record_event` is the ONLY function that writes to security_event.
    Every other surface goes through it so we can centralise PII
    scrubbing if we ever add it.
  - User-id scoping is always passed explicitly — no "ambient user"
    fallback. Cross-user leaks are prevented at the call site, not
    the SQL level.
  - The webhook dispatcher is intentionally tolerant: unknown event
    types are logged-and-ignored, not rejected, so a Clerk feature
    addition doesn't 400 the webhook delivery (which would back up
    Clerk's retry queue).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import clerk_admin
from aicmo.modules.security.models import SecurityEvent, UserSession
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
from aicmo.modules.users.models import User

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------


# Events the internal POST /security/events endpoint will accept.
# Everything else MUST arrive via the Clerk webhook — accepting them
# from the client would let a logged-in user forge "password_change"
# entries in their own timeline.
ALLOWED_CLIENT_EVENTS: frozenset[SecurityEventType] = frozenset(
    {"failed_login", "mfa_challenge"}
)

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
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------
#  Session inventory
# ---------------------------------------------------------------------


async def register_or_touch_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    clerk_session_id: str,
    user_agent: str | None,
    ip_address: str | None,
    geo_country: str | None = None,
    geo_city: str | None = None,
    expires_at: datetime | None = None,
) -> UserSession:
    """Upsert a UserSession row keyed by `clerk_session_id`.

    On INSERT: full row created from the webhook payload.
    On UPDATE: `last_seen_at` bumped + any newly-populated fields filled.
    Revocation columns are NEVER overwritten here — once revoked,
    a session row stays revoked even if Clerk replays an old event.
    """
    now = datetime.now(timezone.utc)
    values = {
        "user_id": user_id,
        "clerk_session_id": clerk_session_id,
        "user_agent": user_agent,
        "ip_address": ip_address,
        "geo_country": geo_country,
        "geo_city": geo_city,
        "expires_at": expires_at,
        "last_seen_at": now,
    }
    stmt = pg_insert(UserSession).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["clerk_session_id"],
        set_={
            "last_seen_at": now,
            "user_agent": func.coalesce(
                UserSession.__table__.c.user_agent,
                stmt.excluded.user_agent,
            ),
            "ip_address": func.coalesce(
                UserSession.__table__.c.ip_address,
                stmt.excluded.ip_address,
            ),
            "geo_country": func.coalesce(
                UserSession.__table__.c.geo_country,
                stmt.excluded.geo_country,
            ),
            "geo_city": func.coalesce(
                UserSession.__table__.c.geo_city,
                stmt.excluded.geo_city,
            ),
            "expires_at": stmt.excluded.expires_at,
            "updated_at": now,
        },
        # Don't touch revoked_at/revoked_by — once gone, stay gone.
    ).returning(UserSession)
    result = await session.execute(stmt)
    return result.scalar_one()


async def list_sessions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_clerk_session_id: str | None,
    include_revoked: bool = False,
    limit: int = 50,
) -> SessionList:
    """List the user's sessions, newest-first. Pins current to flagged."""
    stmt = select(UserSession).where(UserSession.user_id == user_id)
    if not include_revoked:
        stmt = stmt.where(UserSession.revoked_at.is_(None))
    stmt = stmt.order_by(desc(UserSession.last_seen_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return SessionList(
        sessions=[_to_session_read(r, current_clerk_session_id, now) for r in rows]
    )


async def mark_session_revoked(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_row_id: uuid.UUID,
    current_clerk_session_id: str | None,
    actor: str = "self",
    revoked_by: str = "user",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> RevokeSessionResponse:
    """Revoke ONE session row.

    Order of operations:
      1. Load + ownership check (404 vs cross-user leak)
      2. Refuse if it's the current session
      3. Call Clerk admin API (no-raise — returns sentinel)
      4. Mark row revoked locally regardless of remote outcome
      5. Emit `session_revoke` event
      6. Return SessionRead so the UI can replace its row optimistically
    """
    row = await session.get(UserSession, session_row_id)
    if row is None or row.user_id != user_id:
        raise SessionNotFound()
    if row.revoked_at is not None:
        # Idempotent — already revoked. Return current state.
        return RevokeSessionResponse(
            session=_to_session_read(
                row, current_clerk_session_id, datetime.now(timezone.utc)
            ),
            revocation_status=row.revocation_status or "local_only",  # type: ignore[arg-type]
        )

    if (
        current_clerk_session_id is not None
        and row.clerk_session_id == current_clerk_session_id
    ):
        raise CurrentSessionRevokeRefused()

    # Remote revoke (no-raise).
    result = await clerk_admin.revoke_session(row.clerk_session_id)

    # Local mark.
    now = datetime.now(timezone.utc)
    row.revoked_at = now
    row.revoked_by = revoked_by
    row.revocation_status = result.outcome
    row.updated_at = now
    await session.flush()

    # Audit event.
    await record_event(
        session,
        event_type="session_revoke",
        user_id=user_id,
        clerk_session_id=row.clerk_session_id,
        actor=actor,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "revoked_by": revoked_by,
            "clerk_outcome": result.outcome,
            "clerk_detail": result.detail,
        },
    )

    return RevokeSessionResponse(
        session=_to_session_read(row, current_clerk_session_id, now),
        revocation_status=result.outcome,  # type: ignore[arg-type]
    )


async def revoke_all_sessions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_clerk_session_id: str | None,
    actor: str = "self",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> RevokeAllResponse:
    """Revoke every active session for the user EXCEPT the current one.

    We iterate one-by-one so each row gets its own Clerk admin call
    (no batch-revoke endpoint exists on Clerk's side) + its own audit
    event. Skipped-current is reported back so the UI can render
    "5 devices signed out; this one is still active."
    """
    stmt = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    rows = (await session.execute(stmt)).scalars().all()

    revoked_count = 0
    skipped_current = False
    for row in rows:
        if (
            current_clerk_session_id is not None
            and row.clerk_session_id == current_clerk_session_id
        ):
            skipped_current = True
            continue
        await mark_session_revoked(
            session,
            user_id=user_id,
            session_row_id=row.id,
            current_clerk_session_id=current_clerk_session_id,
            actor=actor,
            revoked_by="user",
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
    now = datetime.now(timezone.utc)
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
    recent_event_count = (
        await session.execute(recent_event_count_stmt)
    ).scalar_one()

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


def _is_new_country_login(
    last_login: SecurityEvent | None, *, session_user_id: uuid.UUID
) -> bool:
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
#  Webhook dispatcher
# ---------------------------------------------------------------------


# Map Clerk event types to our handlers. Unknown types are LOGGED and
# accepted (200) — we never 400 the webhook for an unrecognised event.
async def dispatch_webhook(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Route a verified Clerk webhook payload to its handler.

    Returns a dict summarising what was done — used by the router for
    its 200 response body (helps Clerk's webhook log + our own debugging).
    """
    event_type = payload.get("type")
    data = payload.get("data") or {}

    if event_type == "session.created":
        return await _handle_session_created(session, data=data, ip=ip_address)
    if event_type in {"session.ended", "session.removed", "session.revoked"}:
        return await _handle_session_terminated(
            session,
            data=data,
            ip=ip_address,
            terminator=event_type,
        )
    if event_type == "user.updated":
        return await _handle_user_updated(session, data=data, ip=ip_address)
    if event_type in {"user.created", "user.deleted"}:
        # No security-event impact; lifecycle handled by users module
        # webhook in a different phase. Acknowledge cleanly.
        return {"handled": False, "reason": "user_lifecycle_handled_elsewhere"}

    log.info(
        "security.webhook.unknown_event",
        event_type=event_type,
    )
    return {"handled": False, "reason": f"unknown_event_type:{event_type}"}


async def _handle_session_created(
    session: AsyncSession,
    *,
    data: dict[str, Any],
    ip: str | None,
) -> dict[str, Any]:
    clerk_session_id = str(data.get("id") or "")
    clerk_user_id = str(data.get("user_id") or "")
    if not (clerk_session_id and clerk_user_id):
        return {"handled": False, "reason": "missing_ids"}

    user = await _resolve_user(session, clerk_user_id=clerk_user_id)
    if user is None:
        # Webhook arrived before the user's lazy-create. Best effort:
        # log a system event with no user_id rather than swallowing.
        await record_event(
            session,
            event_type="login",
            user_id=None,
            clerk_session_id=clerk_session_id,
            actor="system",
            ip_address=ip,
            metadata={"reason": "user_not_yet_provisioned", "clerk_user_id": clerk_user_id},
        )
        return {"handled": False, "reason": "user_not_found"}

    expires_at = _parse_clerk_ts(data.get("expire_at"))
    last_active_at = _parse_clerk_ts(data.get("last_active_at"))

    row = await register_or_touch_session(
        session,
        user_id=user.id,
        clerk_session_id=clerk_session_id,
        user_agent=data.get("user_agent"),
        ip_address=ip,
        expires_at=expires_at,
    )

    await record_event(
        session,
        event_type="login",
        user_id=user.id,
        clerk_session_id=clerk_session_id,
        actor="self",
        ip_address=ip,
        user_agent=data.get("user_agent"),
        metadata={"clerk_last_active_at": last_active_at.isoformat() if last_active_at else None},
        occurred_at=last_active_at,
    )
    return {"handled": True, "session_row_id": str(row.id)}


async def _handle_session_terminated(
    session: AsyncSession,
    *,
    data: dict[str, Any],
    ip: str | None,
    terminator: str,  # "session.ended" / "session.removed" / "session.revoked"
) -> dict[str, Any]:
    clerk_session_id = str(data.get("id") or "")
    if not clerk_session_id:
        return {"handled": False, "reason": "missing_session_id"}

    # Find our row.
    stmt = select(UserSession).where(
        UserSession.clerk_session_id == clerk_session_id
    )
    row = (await session.execute(stmt)).scalar_one_or_none()

    user_id_for_event: uuid.UUID | None = None
    if row is not None and row.revoked_at is None:
        now = datetime.now(timezone.utc)
        upd = (
            update(UserSession)
            .where(UserSession.id == row.id)
            .values(
                revoked_at=now,
                revoked_by="webhook",
                revocation_status="remote_ok",
                updated_at=now,
            )
        )
        await session.execute(upd)
        user_id_for_event = row.user_id

    if user_id_for_event is None and row is not None:
        user_id_for_event = row.user_id

    # Emit either `logout` (clean end) or `session_revoke` (explicit revoke).
    event_type: SecurityEventType = (
        "session_revoke" if terminator == "session.revoked" else "logout"
    )
    await record_event(
        session,
        event_type=event_type,
        user_id=user_id_for_event,
        clerk_session_id=clerk_session_id,
        actor="system",
        ip_address=ip,
        metadata={"clerk_event": terminator},
    )
    return {"handled": True, "session_row_id": str(row.id) if row else None}


async def _handle_user_updated(
    session: AsyncSession,
    *,
    data: dict[str, Any],
    ip: str | None,
) -> dict[str, Any]:
    """Clerk's `user.updated` fires for any profile change. We only care
    about password changes — detected via the boolean `password_enabled`
    AND a freshly-updated `password_last_updated_at` we cache in
    `user.metadata_unsafe` in a future phase.

    For Phase 10.2c we emit `password_change` whenever the payload
    contains `password_last_updated_at` AND its value is within the
    last 5 minutes (Clerk fires user.updated for many reasons; we
    don't want to emit a security event for every avatar change).
    """
    clerk_user_id = str(data.get("id") or "")
    pwd_updated = _parse_clerk_ts(data.get("password_last_updated_at"))
    if not (clerk_user_id and pwd_updated):
        return {"handled": False, "reason": "not_a_password_change"}

    now = datetime.now(timezone.utc)
    if (now - pwd_updated) > timedelta(minutes=5):
        return {"handled": False, "reason": "password_update_too_old"}

    user = await _resolve_user(session, clerk_user_id=clerk_user_id)
    if user is None:
        return {"handled": False, "reason": "user_not_found"}

    await record_event(
        session,
        event_type="password_change",
        user_id=user.id,
        clerk_session_id=None,
        actor="self",
        ip_address=ip,
        metadata={"clerk_password_updated_at": pwd_updated.isoformat()},
        occurred_at=pwd_updated,
    )
    return {"handled": True, "user_id": str(user.id)}


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


async def _resolve_user(
    session: AsyncSession, *, clerk_user_id: str
) -> User | None:
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _parse_clerk_ts(value: Any) -> datetime | None:
    """Clerk sends timestamps as millisecond-epoch ints. Tolerant of None."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _to_session_read(
    row: UserSession,
    current_clerk_session_id: str | None,
    now: datetime,
) -> SessionRead:
    is_active = row.revoked_at is None and (
        row.expires_at is None or row.expires_at > now
    )
    return SessionRead(
        id=row.id,
        clerk_session_id=row.clerk_session_id,
        user_agent=row.user_agent,
        ip_address=str(row.ip_address) if row.ip_address else None,
        geo_country=row.geo_country,
        geo_city=row.geo_city,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoked_by=row.revoked_by,  # type: ignore[arg-type]
        revocation_status=row.revocation_status,  # type: ignore[arg-type]
        is_current=(
            current_clerk_session_id is not None
            and row.clerk_session_id == current_clerk_session_id
        ),
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
