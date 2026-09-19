"""First-party auth test helpers.

The legitimate way for a test to obtain an authenticated caller: create a real
user row and a real database-backed session, exactly as production does. There
is NO demo bypass, magic token, or fake session — a test authenticates by
sending the same HttpOnly session cookie a browser would.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import sessions
from aicmo.auth.password import hash_password
from aicmo.config import Settings, get_settings
from aicmo.modules.users.models import User


async def create_test_user(
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = "test-password-123",
    verified: bool = True,
) -> User:
    """Insert a real, active user (Argon2id-hashed password, verified email)."""
    user = User(
        email=email or f"test-{uuid.uuid4().hex[:12]}@example.test",
        password_hash=hash_password(password),
        email_verified_at=datetime.now(UTC) if verified else None,
        status="active",
    )
    session.add(user)
    await session.flush()
    return user


async def create_test_session(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings | None = None,
) -> str:
    """Open a real server-side session for `user`. Returns the RAW session
    token — set it as the session cookie to authenticate a request."""
    settings = settings or get_settings()
    raw, _row = await sessions.create_session(session, user_id=user.id, settings=settings)
    return raw
