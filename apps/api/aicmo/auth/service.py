"""First-party account lifecycle.

Orchestrates users + passwords + sessions + email tokens + throttling. Two
cross-cutting rules shape every function here:

  * Enumeration safety — signup, signin, and password-reset requests never
    reveal whether an email is registered. Callers get a generic result; the
    difference is only in which (if any) email we send.
  * Session invalidation on credential change — any password change (reset or
    authenticated change) revokes all of the user's existing sessions.

Nothing here logs a password or a raw token.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import email_tokens, sessions, throttle
from aicmo.auth.email import get_email_sender
from aicmo.auth.models import UserSession
from aicmo.auth.password import hash_password, needs_rehash, verify_password
from aicmo.config import Settings
from aicmo.modules.users.models import User

# Password policy. Argon2id handles arbitrary length; the cap only prevents a
# multi-megabyte body from tying up a hashing thread.
MIN_PASSWORD_LEN = 10
MAX_PASSWORD_LEN = 128


class WeakPassword(ValueError):
    """Raised when a proposed password fails policy. Safe to surface (it says
    nothing about any account)."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_password(password: str) -> None:
    if not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        raise WeakPassword(f"Password must be {MIN_PASSWORD_LEN}-{MAX_PASSWORD_LEN} characters.")


async def get_user_by_email(session: AsyncSession, *, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == _normalize_email(email)))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------
#  Sign up
# ---------------------------------------------------------------------


async def signup(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None,
    settings: Settings,
) -> None:
    """Create a new unverified account and send a verification link.

    Enumeration-safe: returns None regardless of whether the email was new.
    If the email already exists we do NOT create a second row or change the
    existing password — we just (re)send the appropriate email.
    """
    _validate_password(password)
    norm = _normalize_email(email)
    existing = await get_user_by_email(session, email=norm)
    sender = get_email_sender()

    if existing is not None:
        # Don't reveal existence. If they never verified, resend verification;
        # otherwise nudge them to sign in / reset. Never mutate credentials.
        if existing.email_verified_at is None and existing.status == "active":
            raw = await email_tokens.issue_token(
                session,
                user_id=existing.id,
                purpose="verify",
                ttl_seconds=settings.email_verify_ttl_seconds,
            )
            await sender.send_verification(to=norm, link=_verify_link(settings, raw))
        return

    user = User(
        email=norm,
        display_name=display_name,
        password_hash=hash_password(password),
        status="active",
    )
    session.add(user)
    await session.flush()
    raw = await email_tokens.issue_token(
        session,
        user_id=user.id,
        purpose="verify",
        ttl_seconds=settings.email_verify_ttl_seconds,
    )
    await sender.send_verification(to=norm, link=_verify_link(settings, raw))


# ---------------------------------------------------------------------
#  Email verification
# ---------------------------------------------------------------------


async def verify_email(session: AsyncSession, *, raw_token: str, settings: Settings) -> bool:
    user_id = await email_tokens.consume_token(session, raw_token=raw_token, purpose="verify")
    if user_id is None:
        return False
    user = await session.get(User, user_id)
    if user is None:
        return False
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return True


# ---------------------------------------------------------------------
#  Sign in
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class SigninResult:
    ok: bool
    locked: bool = False
    user: User | None = None
    session_token: str | None = None
    user_session: UserSession | None = None


async def signin(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings,
    ip: str | None = None,
    user_agent: str | None = None,
) -> SigninResult:
    """Authenticate and, on success, open a session. Generic on every failure
    (unknown email, wrong password, unverified, disabled) so nothing leaks."""
    norm = _normalize_email(email)

    if await throttle.is_locked_out(session, email=norm, ip=ip, settings=settings):
        return SigninResult(ok=False, locked=True)

    user = await get_user_by_email(session, email=norm)

    # Always run a hash verification to keep timing uniform between
    # existing and non-existing accounts (mitigates user enumeration by
    # response time). For a missing user we verify against a throwaway hash.
    stored = user.password_hash if (user and user.password_hash) else _DUMMY_HASH
    password_ok = verify_password(stored, password)

    valid = bool(
        user
        and user.password_hash
        and password_ok
        and user.status == "active"
        and (user.email_verified_at is not None or not settings.auth_require_verified_email)
    )

    await throttle.record_attempt(session, email=norm, ip=ip, successful=valid)
    if not valid or user is None:
        return SigninResult(ok=False)

    # Opportunistic rehash if the stored hash used weaker params.
    if needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(password)

    raw, row = await sessions.create_session(
        session, user_id=user.id, settings=settings, ip=ip, user_agent=user_agent
    )
    user.last_seen_at = datetime.now(UTC)
    return SigninResult(ok=True, user=user, session_token=raw, user_session=row)


# A valid Argon2id hash of a random string, used to equalise verify timing for
# non-existent accounts. Never matches any real password.
_DUMMY_HASH = hash_password(uuid.uuid4().hex)


# ---------------------------------------------------------------------
#  Password reset (unauthenticated) + change (authenticated)
# ---------------------------------------------------------------------


async def request_password_reset(session: AsyncSession, *, email: str, settings: Settings) -> None:
    """Enumeration-safe: always returns None. Sends a reset link only if the
    account exists and is active."""
    norm = _normalize_email(email)
    user = await get_user_by_email(session, email=norm)
    if user is None or user.status != "active":
        return
    raw = await email_tokens.issue_token(
        session,
        user_id=user.id,
        purpose="reset",
        ttl_seconds=settings.password_reset_ttl_seconds,
    )
    await get_email_sender().send_password_reset(to=norm, link=_reset_link(settings, raw))


async def reset_password(
    session: AsyncSession, *, raw_token: str, new_password: str, settings: Settings
) -> bool:
    """Consume a reset token, set the new password, and revoke ALL of the
    user's sessions (the reset itself is proof the old ones may be compromised)."""
    _validate_password(new_password)
    user_id = await email_tokens.consume_token(session, raw_token=raw_token, purpose="reset")
    if user_id is None:
        return False
    user = await session.get(User, user_id)
    if user is None:
        return False
    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(UTC)
    # A verified reset also proves control of the mailbox → mark verified.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await sessions.revoke_all_for_user(session, user_id=user.id)
    await session.flush()
    return True


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
    settings: Settings,
    keep_session_id: uuid.UUID | None = None,
) -> bool:
    """Authenticated change. Verifies the current password, sets the new one,
    and revokes every OTHER session (the caller's current session is kept via
    keep_session_id, then rotated by the router)."""
    if not (user.password_hash and verify_password(user.password_hash, current_password)):
        return False
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(UTC)
    await sessions.revoke_all_for_user(session, user_id=user.id, except_session_id=keep_session_id)
    await session.flush()
    return True


async def disable_account(session: AsyncSession, *, user: User) -> None:
    """Suspend the account and revoke all sessions."""
    user.status = "suspended"
    await sessions.revoke_all_for_user(session, user_id=user.id)
    await session.flush()


# ---------------------------------------------------------------------
#  Link builders
# ---------------------------------------------------------------------


def _verify_link(settings: Settings, raw_token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/verify-email?token={raw_token}"


def _reset_link(settings: Settings, raw_token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/reset-password?token={raw_token}"
