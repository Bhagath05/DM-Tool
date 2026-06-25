"""Postgres-backed rate limiter.

Fixed-window. Cheap UPSERT per request. No Redis. Designed to scale to
~10k captures/day without thought; beyond that the right move is to swap
this implementation for Redis INCR — same call signature, one-file change.

Why fixed-window not sliding-log: sliding-log requires storing every
request timestamp; fixed-window stores one row per (key, minute). 60x
fewer writes.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.security.models import RateLimitBucket

# 1-minute fixed window. Tune via env if needed later.
_WINDOW_SECONDS = 60
_CLEANUP_PROBABILITY = 0.01  # 1% of submits trigger a cleanup
_CLEANUP_RETENTION = timedelta(hours=1)


def _window_start(now: datetime) -> datetime:
    """Round down to the current minute."""
    return now.replace(second=0, microsecond=0)


async def consume(
    session: AsyncSession,
    *,
    key: str,
    limit: int,
) -> None:
    """Atomically increment the bucket and raise 429 if over limit.

    UPSERT pattern: insert with count=1 OR add 1 to the existing row,
    returning the post-increment count. One round trip.
    """
    now = datetime.now(UTC)
    window = _window_start(now)

    stmt = (
        pg_insert(RateLimitBucket)
        .values(key=key, window_start=window, count=1)
        .on_conflict_do_update(
            constraint="uq_rl_key_window",
            set_={"count": RateLimitBucket.__table__.c.count + 1},
        )
        .returning(RateLimitBucket.count)
    )
    result = await session.execute(stmt)
    new_count = result.scalar_one()
    await session.commit()

    if new_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again in a minute.",
        )

    # Opportunistic cleanup — keeps the table from growing unbounded
    # without any cron job. Statistically every ~100th submit triggers it.
    if random.random() < _CLEANUP_PROBABILITY:
        await cleanup_stale(session)


async def cleanup_stale(session: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - _CLEANUP_RETENTION
    await session.execute(
        delete(RateLimitBucket).where(RateLimitBucket.window_start < cutoff)
    )
    await session.commit()


def hash_ip(ip: str) -> str:
    """SHA-256 with a per-server pepper. Never store raw IPs (GDPR)."""
    settings = get_settings()
    pepper = (settings.ip_hash_pepper or "dev-pepper").encode()
    return hashlib.sha256(pepper + ip.encode()).hexdigest()[:32]
