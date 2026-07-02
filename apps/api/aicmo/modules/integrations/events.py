"""Phase 6.1 — integration activity log (Sync History / Error Center / Analytics).

`record_event` is the single, additive write hook the existing service calls at
its OAuth / sync / disconnect / error points (it only stages the row; the
service's existing commit persists it). The read helpers power the enterprise
management surfaces from this one append-only table — no duplication of the
connection/credential storage.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.integrations.models import IntegrationConnection, IntegrationEvent


def record_event(
    session: AsyncSession,
    *,
    connection: IntegrationConnection,
    event_type: str,
    status: str = "info",
    message: str | None = None,
    detail: dict | None = None,
    duration_ms: int | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Stage one activity-log row from a connection. Does NOT commit — the
    caller (the existing service function) owns the transaction. Never logs a
    secret; `message` is truncated defensively."""
    session.add(
        IntegrationEvent(
            id=uuid.uuid4(),
            organization_id=connection.organization_id,
            brand_id=connection.brand_id,
            connection_id=connection.id,
            provider_slug=connection.provider_slug,
            event_type=event_type,
            status=status,
            message=(message or "")[:500] or None,
            detail=detail or {},
            duration_ms=duration_ms,
            occurred_at=occurred_at or datetime.now(UTC),
        )
    )


async def list_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    provider_slug: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[IntegrationEvent]:
    """Tenant-scoped event feed. Filters power Activity Logs (no filter), Sync
    History (event_type prefix 'sync'), and the Error Center (status='failure')."""
    stmt = select(IntegrationEvent).where(
        IntegrationEvent.organization_id == organization_id
    )
    if brand_id is not None:
        stmt = stmt.where(IntegrationEvent.brand_id == brand_id)
    if connection_id is not None:
        stmt = stmt.where(IntegrationEvent.connection_id == connection_id)
    if provider_slug:
        stmt = stmt.where(IntegrationEvent.provider_slug == provider_slug)
    if event_type:
        stmt = stmt.where(IntegrationEvent.event_type == event_type)
    if status:
        stmt = stmt.where(IntegrationEvent.status == status)
    stmt = stmt.order_by(desc(IntegrationEvent.occurred_at)).limit(
        max(1, min(limit, 500))
    )
    return list((await session.execute(stmt)).scalars().all())


async def analytics(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None = None,
    days: int = 30,
) -> dict:
    """Aggregate integration health/usage for the Integration Analytics surface.
    Pure counts over real rows — no fabrication."""
    since = datetime.now(UTC) - timedelta(days=days)

    # Connection states.
    cstmt = select(IntegrationConnection.state).where(
        IntegrationConnection.organization_id == organization_id
    )
    if brand_id is not None:
        cstmt = cstmt.where(IntegrationConnection.brand_id == brand_id)
    conn_states = Counter(
        row[0] for row in (await session.execute(cstmt)).all()
    )

    # Recent events.
    estmt = select(
        IntegrationEvent.event_type,
        IntegrationEvent.status,
        IntegrationEvent.provider_slug,
    ).where(
        IntegrationEvent.organization_id == organization_id,
        IntegrationEvent.occurred_at >= since,
    )
    if brand_id is not None:
        estmt = estmt.where(IntegrationEvent.brand_id == brand_id)
    rows = (await session.execute(estmt)).all()

    syncs = [r for r in rows if r[0] in ("sync_completed", "sync_failed")]
    sync_ok = sum(1 for r in syncs if r[1] == "success")
    sync_fail = sum(1 for r in syncs if r[1] == "failure")
    errors = sum(1 for r in rows if r[1] == "failure")
    by_provider = Counter(r[2] for r in rows)

    total_syncs = sync_ok + sync_fail
    success_rate = round(sync_ok / total_syncs, 4) if total_syncs else None

    return {
        "window_days": days,
        "connections_total": sum(conn_states.values()),
        "connections_by_state": dict(conn_states),
        "syncs_total": total_syncs,
        "syncs_succeeded": sync_ok,
        "syncs_failed": sync_fail,
        "sync_success_rate": success_rate,
        "errors_total": errors,
        "events_total": len(rows),
        "events_by_provider": dict(by_provider),
    }
