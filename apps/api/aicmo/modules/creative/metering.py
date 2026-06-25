"""Creative usage metering — the customer's quota (Creative Core V0).

Reuses the Phase-1 billing layer: `video_generation` (per-video quota) +
`video_second` (per-second usage). Plus a per-user daily render cap (video
is expensive). All soft in V0 — record-only; never blocks while
`billing_enforce_limits` is off and the cap is informational.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.billing import billing_live
from aicmo.modules.billing.models import UsageEvent


@dataclass(frozen=True, slots=True)
class DailyCapStatus:
    used_today: int
    cap: int
    over: bool


async def enforce_video_quota(session: AsyncSession, *, organization_id: uuid.UUID):
    """Soft plan-quota gate for video_generation. Returns the QuotaStatus;
    raises 402 only when enforcement is enabled AND over limit (reuses the
    billing gate). Fails open."""
    return await billing_live.enforce_quota(
        session, organization_id=organization_id, kind="video_generation"
    )


async def check_daily_cap(
    session: AsyncSession, *, organization_id: uuid.UUID, user_uuid: uuid.UUID | None
) -> DailyCapStatus:
    """Per-user daily video render count vs `video_render_daily_cap`.
    Informational in V0 (the start endpoint surfaces it); becomes a hard
    block when enforcement is turned on."""
    cap = get_settings().video_render_daily_cap
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.coalesce(func.sum(UsageEvent.quantity), 0))
        .where(UsageEvent.organization_id == organization_id)
        .where(UsageEvent.kind == "video_generation")
        .where(UsageEvent.occurred_at >= start)
    )
    if user_uuid is not None:
        stmt = stmt.where(UsageEvent.user_id == user_uuid)
    used = int((await session.execute(stmt)).scalar_one())
    return DailyCapStatus(used_today=used, cap=cap, over=cap > 0 and used >= cap)


async def record_video_usage(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_uuid: uuid.UUID | None,
    brand_id: uuid.UUID | None,
    seconds: int,
) -> None:
    """Record BOTH metered kinds for one finished video (Decision 3)."""
    await billing_live.record_metered(
        session,
        organization_id=organization_id,
        kind="video_generation",
        user_id=user_uuid,
        brand_id=brand_id,
        quantity=1,
        metadata={"media_type": "video"},
    )
    if seconds > 0:
        await billing_live.record_metered(
            session,
            organization_id=organization_id,
            kind="video_second",
            user_id=user_uuid,
            brand_id=brand_id,
            quantity=seconds,
            metadata={"media_type": "video"},
        )
