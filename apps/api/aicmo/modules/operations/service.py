"""Phase 4 — Operations tenant-scoped reads (for the Ops dashboard, 4.7)."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations import monitoring
from aicmo.modules.operations.models import DetectedEvent
from aicmo.modules.operations.schemas import (
    DetectedEventResponse,
    EventsView,
    MetricSnapshotResponse,
    MonitoringView,
)


async def monitoring_view(
    session: AsyncSession, *, brand_id: uuid.UUID, history: int = 20
) -> MonitoringView:
    rows = await monitoring.recent_snapshots(session, brand_id=brand_id, limit=history)
    items = [MetricSnapshotResponse.model_validate(r) for r in rows]
    latest = items[0] if items else None
    return MonitoringView(
        latest=latest,
        history=items,
        monitored=bool(items),
        note=None
        if items
        else "No monitoring data yet — the operations loop hasn't captured a snapshot for this brand.",
    )


async def events_view(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    only_open: bool = False,
    limit: int = 50,
) -> EventsView:
    stmt = select(DetectedEvent).where(DetectedEvent.brand_id == brand_id)
    if only_open:
        stmt = stmt.where(DetectedEvent.status.in_(("new", "acknowledged")))
    stmt = stmt.order_by(desc(DetectedEvent.detected_at)).limit(max(1, min(limit, 200)))
    rows = list((await session.execute(stmt)).scalars().all())
    items = [DetectedEventResponse.model_validate(r) for r in rows]
    open_count = sum(1 for r in rows if r.status in ("new", "acknowledged"))
    return EventsView(
        items=items,
        open_count=open_count,
        note=None if items else "No events detected yet.",
    )
