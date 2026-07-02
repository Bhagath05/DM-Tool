"""Phase 4.1 — Continuous Monitoring Engine.

Captures a brand's REAL metrics by REUSING the existing services (analytics,
performance, publishing) — no new collectors, no re-derivation. Cheap (no LLM).
Idempotent per cadence: a brand isn't re-snapshotted within
`operations_monitor_interval_seconds`, so repeated ticks are no-ops.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.operations.models import MetricSnapshot

log = structlog.get_logger()


async def latest_snapshot(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> MetricSnapshot | None:
    stmt = (
        select(MetricSnapshot)
        .where(MetricSnapshot.brand_id == brand_id)
        .order_by(desc(MetricSnapshot.captured_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def recent_snapshots(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int = 30
) -> list[MetricSnapshot]:
    stmt = (
        select(MetricSnapshot)
        .where(MetricSnapshot.brand_id == brand_id)
        .order_by(desc(MetricSnapshot.captured_at))
        .limit(max(1, min(limit, 200)))
    )
    return list((await session.execute(stmt)).scalars().all())


async def _gather_metrics(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[dict, list[str]]:
    """Reuse existing services to read a brand's real metrics. Each source is
    guarded so a degraded source yields a partial (honest) snapshot."""
    metrics: dict = {}
    ok: list[str] = []

    try:
        from aicmo.modules.analytics import service as analytics_service

        k = await analytics_service.overview(session, brand_id=brand_id)
        metrics.update(
            total_leads=k.total_leads,
            leads_7d=k.leads_7d,
            leads_30d=k.leads_30d,
            hot_leads=k.hot_leads,
            total_views=k.total_views,
            conversion_rate=round(k.conversion_rate, 6),
            landing_pages_published=k.landing_pages_published,
        )
        ok.append("analytics")
    except Exception as e:
        log.warning("ops.monitor.analytics_failed", error=str(e)[:120])

    try:
        from aicmo.modules.performance import service as performance_service

        # performance.overview only reads tenant.brand_id — a light ctx suffices.
        perf = await performance_service.overview(
            session, tenant=SimpleNamespace(brand_id=brand_id)
        )
        metrics.update(
            performance_has_data=perf.has_data,
            performance_rows=perf.rows_ingested,
            creatives_tracked=perf.creatives_tracked,
            performance_diagnostics=len(perf.diagnostics),
        )
        ok.append("performance")
    except Exception as e:
        log.warning("ops.monitor.performance_failed", error=str(e)[:120])

    try:
        from aicmo.modules.publishing import service as publishing_service

        sched = await publishing_service.list_scheduled(
            session, brand_id=brand_id, limit=200
        )
        published = scheduled = failed = 0
        for item in sched.items:
            if item.publish_status == "published":
                published += 1
            elif item.publish_status == "failed":
                failed += 1
            elif item.publish_status == "scheduled":
                scheduled += 1
        metrics.update(
            published_posts=published,
            scheduled_posts=scheduled,
            failed_posts=failed,
        )
        ok.append("publishing")
    except Exception as e:
        log.warning("ops.monitor.publishing_failed", error=str(e)[:120])

    return metrics, ok


async def capture_brand_snapshot(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    now: datetime | None = None,
    force: bool = False,
) -> tuple[bool, str, dict]:
    """Capture one snapshot for a brand, respecting the per-brand cadence.
    Returns (captured, reason, metrics). Does NOT commit — the caller owns the
    transaction so a whole cycle commits once."""
    now = now or datetime.now(UTC)
    interval = get_settings().operations_monitor_interval_seconds

    if not force:
        last = await latest_snapshot(session, brand_id=brand_id)
        if last is not None and last.captured_at > now - timedelta(seconds=interval):
            return False, "within_cadence", dict(last.metrics or {})

    metrics, ok = await _gather_metrics(session, brand_id=brand_id)
    if not ok:
        # Every source degraded — record nothing rather than an empty snapshot.
        return False, "sources_unavailable", {}

    session.add(
        MetricSnapshot(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_id=brand_id,
            captured_at=now,
            metrics=metrics,
            sources_ok=ok,
        )
    )
    return True, "captured", metrics
