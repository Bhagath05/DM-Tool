"""Phase 4 — Operations tenant-scoped reads (for the Ops dashboard, 4.7)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations import monitoring
from aicmo.modules.operations.schemas import (
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
