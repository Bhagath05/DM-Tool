"""Phase 4 — Operations tenant-scoped reads (for the Ops dashboard, 4.7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations import monitoring
from aicmo.modules.operations.models import (
    DetectedEvent,
    OperationsNotification,
    ScheduledWork,
)
from aicmo.modules.operations.schemas import (
    DetectedEventResponse,
    EventsView,
    MetricSnapshotResponse,
    MonitoringView,
    NotificationList,
    NotificationResponse,
    WorkItemResponse,
    WorkList,
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


async def work_view(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    status: str | None = None,
    limit: int = 50,
) -> WorkList:
    stmt = select(ScheduledWork).where(ScheduledWork.brand_id == brand_id)
    if status:
        stmt = stmt.where(ScheduledWork.status == status)
    stmt = stmt.order_by(desc(ScheduledWork.created_at)).limit(max(1, min(limit, 200)))
    rows = list((await session.execute(stmt)).scalars().all())
    items = [WorkItemResponse.model_validate(r) for r in rows]
    awaiting = sum(1 for r in rows if r.status == "awaiting_approval")
    return WorkList(items=items, awaiting_approval=awaiting)


async def set_work_status(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    work_id: uuid.UUID,
    status: str,
) -> ScheduledWork | None:
    row = await session.get(ScheduledWork, work_id)
    if row is None or row.brand_id != brand_id:
        return None
    row.status = status
    await session.flush()
    return row


# ---------------------------------------------------------------------
#  4.8 — Notification feed
# ---------------------------------------------------------------------
async def notifications_view(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    only_unread: bool = False,
    limit: int = 50,
) -> NotificationList:
    stmt = select(OperationsNotification).where(
        OperationsNotification.brand_id == brand_id
    )
    if only_unread:
        stmt = stmt.where(OperationsNotification.read.is_(False))
    stmt = stmt.order_by(desc(OperationsNotification.created_at)).limit(
        max(1, min(limit, 200))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    items = [NotificationResponse.model_validate(r) for r in rows]
    unread = sum(1 for r in rows if not r.read)
    return NotificationList(items=items, unread=unread)


async def mark_notification_read(
    session: AsyncSession, *, brand_id: uuid.UUID, notification_id: uuid.UUID
) -> OperationsNotification | None:
    row = await session.get(OperationsNotification, notification_id)
    if row is None or row.brand_id != brand_id:
        return None
    row.read = True
    await session.flush()
    return row


# ---------------------------------------------------------------------
#  4.7 — Operations dashboard (pure aggregation of existing reads)
# ---------------------------------------------------------------------
async def dashboard(session: AsyncSession, *, tenant):
    """Compose the live Ops dashboard. Every sub-read is guarded so a degraded
    source never sinks the page. Reuses operations + Phase-3 reads — no new
    intelligence."""
    import structlog

    from aicmo.modules.operations import goals as goals_mod
    from aicmo.modules.operations.models import OperationsRun
    from aicmo.modules.operations.schemas import (
        OperationsAutonomyStatus,
        OperationsDashboard,
        OperationsSystemStatus,
    )

    log = structlog.get_logger()
    brand_id = tenant.brand_id
    now = datetime.now(UTC)

    mon = await monitoring_view(session, brand_id=brand_id, history=1)
    evv = await events_view(session, brand_id=brand_id, only_open=True, limit=8)
    wv = await work_view(session, brand_id=brand_id, status="awaiting_approval", limit=10)

    active_goals = []
    try:
        rows = await goals_mod.list_goals(session, brand_id=brand_id, only_active=True)
        active_goals = [goals_mod.to_response(r) for r in rows[:5]]
    except Exception as e:
        log.warning("ops.dashboard.goals_failed", error=str(e)[:120])

    learnings: list[dict] = []
    try:
        from aicmo.modules.learning import insights_service

        rows = await insights_service.list_insights(
            session, brand_id=brand_id, only_active=True, limit=5
        )
        learnings = [r.model_dump(mode="json") for r in rows]
    except Exception as e:
        log.warning("ops.dashboard.learnings_failed", error=str(e)[:120])

    autonomy = OperationsAutonomyStatus(
        autonomy_level="manual", execution_enabled=False, configured=False
    )
    try:
        from aicmo.modules.autonomy import service as autonomy_service

        cfg = await autonomy_service.get_or_default(session, brand_id=brand_id)
        autonomy = OperationsAutonomyStatus(
            autonomy_level=cfg.autonomy_level,
            execution_enabled=cfg.execution_enabled,
            configured=cfg.configured,
        )
    except Exception as e:
        log.warning("ops.dashboard.autonomy_failed", error=str(e)[:120])

    lifecycle: dict = {}
    try:
        from aicmo.modules.orchestrator import service as orch

        plan = await orch.build_plan(session, tenant=tenant)
        lifecycle = plan.model_dump(mode="json")
    except Exception as e:
        log.warning("ops.dashboard.lifecycle_failed", error=str(e)[:120])

    last_run = (
        await session.execute(
            select(OperationsRun).order_by(desc(OperationsRun.started_at)).limit(1)
        )
    ).scalar_one_or_none()
    system = OperationsSystemStatus(
        last_run_at=last_run.started_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
        last_brands_scanned=last_run.brands_scanned if last_run else 0,
        monitored=mon.monitored,
    )

    # Plain-language headline.
    if wv.awaiting_approval:
        headline = f"{wv.awaiting_approval} item(s) need your approval, and {evv.open_count} open signal(s) to review."
    elif evv.open_count:
        headline = f"{evv.open_count} signal(s) detected — the AI is preparing recommendations."
    elif not mon.monitored:
        headline = "The operations loop hasn't run yet for this brand — enable it to start continuous monitoring."
    else:
        headline = "All quiet — the AI is monitoring and will surface work when something changes."

    return OperationsDashboard(
        generated_at=now.isoformat(),
        headline=headline,
        system=system,
        autonomy=autonomy,
        latest_metrics=mon.latest,
        open_events=evv.items,
        open_event_count=evv.open_count,
        active_goals=active_goals,
        work_awaiting_approval=wv.items,
        awaiting_approval_count=wv.awaiting_approval,
        recent_learnings=learnings,
        lifecycle=lifecycle,
    )
