"""Single-use email/reset token store.

Same discipline as sessions: the raw token goes only into the emailed link; we
persist its SHA-256 hash. A token is redeemable exactly once — `consume` checks
purpose, expiry, and unused-ness, then stamps `used_at` in the same call so a
replay finds it already spent. Issuing a fresh token invalidates the user's
prior unspent tokens of the same purpose, so an old link can't be revived.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.models import EmailToken
from aicmo.auth.tokens import generate_token, hash_token


async def issue_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: str,
    ttl_seconds: int,
) -> str:
    """Invalidate the user's prior unspent tokens of this purpose, then mint a
    fresh one. Returns the RAW token (store only the hash)."""
    now = datetime.now(UTC)
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = generate_token()
    session.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    await session.flush()
    return raw


async def consume_token(session: AsyncSession, *, raw_token: str, purpose: str) -> uuid.UUID | None:
    """Redeem a token. Returns the user_id on success (and marks it used), or
    None if unknown / wrong purpose / expired / already used."""
    if not raw_token:
        return None
    row = (
        await session.execute(
            select(EmailToken).where(EmailToken.token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if row is None or row.purpose != purpose:
        return None
    now = datetime.now(UTC)
    if row.used_at is not None or row.expires_at <= now:
        return None
    row.used_at = now
    await session.flush()
    return row.user_id
