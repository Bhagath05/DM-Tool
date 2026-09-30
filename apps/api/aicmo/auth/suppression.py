"""Auth email suppression store.

A first-party record of destination addresses that are permanently
undeliverable. The auth delivery path checks it before sending and skips a
suppressed address; a terminal recipient rejection writes it. The identity is
the NORMALIZED email (the destination), so changing a user's email to a fresh
address is never blocked by an old suppressed one.

This is the minimal persistence + short-circuit foundation only — no bounce/DSN
processing. A future real-MTA bounce pipeline can call ``suppress_email`` with
its own reason/source.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.models import EmailSuppression


def normalize_email(email: str | None) -> str:
    """Same normalization the auth service uses for user emails."""
    return (email or "").strip().lower()


async def is_email_suppressed(session: AsyncSession, email: str | None) -> bool:
    """True iff this destination address is on the suppression list."""
    norm = normalize_email(email)
    if not norm:
        return False
    row = (
        await session.execute(
            select(EmailSuppression.id).where(EmailSuppression.email == norm)
        )
    ).first()
    return row is not None


async def suppress_email(
    session: AsyncSession,
    *,
    email: str | None,
    user_id: uuid.UUID | None,
    reason: str,
    source: str,
    meta: dict | None = None,
) -> None:
    """Idempotently record a destination address as suppressed.

    Keyed by the normalized email, so repeated permanent-failure events for the
    same address update the existing row (reason/source/user/updated_at) instead
    of creating duplicates. ``meta`` must hold only non-sensitive operational
    data — never a token, link, or credential. No-op for an empty address."""
    norm = normalize_email(email)
    if not norm:
        return
    stmt = (
        pg_insert(EmailSuppression)
        .values(
            email=norm,
            user_id=user_id,
            reason=reason,
            source=source,
            meta=meta or {},
        )
        .on_conflict_do_update(
            index_elements=[EmailSuppression.email],
            set_={
                "reason": reason,
                "source": source,
                "user_id": user_id,
                "meta": meta or {},
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(stmt)
