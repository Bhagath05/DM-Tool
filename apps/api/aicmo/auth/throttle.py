"""Login throttling backed by the login_attempts ledger.

Counts recent FAILED attempts within a rolling window, per account (email) and
per source IP, and locks further attempts once either threshold is crossed.
Per-IP limits blunt credential stuffing across many accounts; per-account
limits blunt brute force against one account. A successful login is recorded
too (for audit) but never counts toward a lockout.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.models import LoginAttempt
from aicmo.config import Settings


async def record_attempt(
    session: AsyncSession,
    *,
    email: str | None,
    ip: str | None,
    successful: bool,
) -> None:
    session.add(
        LoginAttempt(
            email=(email or "").strip().lower() or None,
            ip=ip,
            successful=successful,
        )
    )
    await session.flush()


async def is_locked_out(
    session: AsyncSession, *, email: str | None, ip: str | None, settings: Settings
) -> bool:
    """True if recent failures for this account OR this IP exceed policy."""
    window_start = datetime.now(UTC) - timedelta(seconds=settings.login_attempt_window_seconds)
    norm_email = (email or "").strip().lower() or None

    if norm_email:
        account_fails = (
            await session.execute(
                select(func.count())
                .select_from(LoginAttempt)
                .where(
                    LoginAttempt.email == norm_email,
                    LoginAttempt.successful.is_(False),
                    LoginAttempt.created_at >= window_start,
                )
            )
        ).scalar_one()
        if account_fails >= settings.login_max_attempts_per_account:
            return True

    if ip:
        ip_fails = (
            await session.execute(
                select(func.count())
                .select_from(LoginAttempt)
                .where(
                    LoginAttempt.ip == ip,
                    LoginAttempt.successful.is_(False),
                    LoginAttempt.created_at >= window_start,
                )
            )
        ).scalar_one()
        if ip_fails >= settings.login_max_attempts_per_ip:
            return True

    return False
