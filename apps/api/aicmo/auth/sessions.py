"""Server-side session store.

The raw session token exists only in transit (the cookie) and in the caller's
hands for the moment after creation. Everything here works off its SHA-256
hash. A session authenticates a request iff a row exists for that hash AND the
row is neither revoked nor expired.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.models import UserSession
from aicmo.auth.tokens import generate_token, hash_token
from aicmo.config import Settings


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, UserSession]:
    """Mint a new session. Returns (raw_token, row). The raw token is the only
    time the secret is available — hand it straight to the cookie."""
    raw = generate_token()
    now = datetime.now(UTC)
    row = UserSession(
        user_id=user_id,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        last_used_at=now,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(row)
    await session.flush()
    return raw, row


async def resolve_session(session: AsyncSession, *, raw_token: str) -> UserSession | None:
    """Return the active UserSession for a raw token, or None if it is unknown,
    revoked, or expired. Updates last_used_at on a hit."""
    if not raw_token:
        return None
    row = (
        await session.execute(
            select(UserSession).where(UserSession.token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        return None
    if row.expires_at <= now:
        return None
    row.last_used_at = now
    return row


async def rotate_if_stale(
    session: AsyncSession, *, user_session: UserSession, settings: Settings
) -> str | None:
    """If the session token is older than the rotation window, issue a fresh
    token (new hash + refreshed expiry) and return the new raw token; else
    None. Session identity (row id, user) is preserved — only the secret
    rotates, which defeats fixation and shrinks the stolen-token window."""
    now = datetime.now(UTC)
    age = now - (user_session.created_at or now)
    if age < timedelta(seconds=settings.session_rotate_after_seconds):
        return None
    raw = generate_token()
    user_session.token_hash = hash_token(raw)
    user_session.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    user_session.last_used_at = now
    # Reset the rotation clock so we rotate at most once per window, not on
    # every request after it. The row id (session identity) is unchanged.
    user_session.created_at = now
    await session.flush()
    return raw


async def revoke_session(session: AsyncSession, *, user_session: UserSession) -> None:
    if user_session.revoked_at is None:
        user_session.revoked_at = datetime.now(UTC)
        await session.flush()


async def revoke_all_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    except_session_id: uuid.UUID | None = None,
) -> int:
    """Revoke every active session for a user (used on password change / reset
    and 'log out everywhere'). Optionally keep one session alive (the caller's).
    Returns the number revoked."""
    now = datetime.now(UTC)
    stmt = (
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    result = await session.execute(stmt)
    # `rowcount` is on the CursorResult returned by an UPDATE; the base Result
    # type doesn't declare it, so this is a typing-only narrowing.
    return result.rowcount or 0  # type: ignore[attr-defined]
