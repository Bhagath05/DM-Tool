"""Phase 4 — the driver-agnostic continuous-loop core.

`run_operations_cycle` is the ONE place the loop's business logic lives. It is
invoked identically by:
  - the guarded `POST /operations/tick` endpoint (today), and
  - the Arq worker cron (future, once Redis + worker are provisioned).

Swapping drivers means pointing a new caller at this function — nothing here or
downstream changes. Every operation is tenant-scoped; the cycle iterates active
brands system-wide (RLS-bypassed, like the existing publish cron) and delegates
per-brand work to the reused Phase-3/4 services.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.operations import events, monitoring
from aicmo.modules.operations.models import OperationsRun
from aicmo.modules.operations.schemas import BrandCycleResult, TickResult

log = structlog.get_logger()


async def _recent_run(session: AsyncSession) -> OperationsRun | None:
    stmt = select(OperationsRun).order_by(desc(OperationsRun.started_at)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _active_brands(session: AsyncSession) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(brand_id, organization_id) for every active brand, system-wide."""
    from aicmo.modules.orgs.models import Brand

    stmt = select(Brand.id, Brand.organization_id).where(Brand.status == "active")
    rows = (await session.execute(stmt)).all()
    return [(r[0], r[1]) for r in rows]


async def run_operations_cycle(
    session: AsyncSession,
    *,
    trigger: str = "api",
    now: datetime | None = None,
) -> TickResult:
    """Run ONE continuous-loop cycle across all active brands. Idempotent within
    the configured cadence; commits once. Never raises — a per-brand failure is
    recorded and the cycle continues."""
    started = now or datetime.now(UTC)
    settings = get_settings()

    # Global throttle (rate-limit) — skip if a cycle ran very recently.
    last = await _recent_run(session)
    if last is not None and last.started_at > started - timedelta(
        seconds=settings.operations_tick_min_gap_seconds
    ):
        return TickResult(
            trigger=trigger,
            status="throttled",
            note="A cycle ran moments ago — try again shortly.",
        )

    run = OperationsRun(
        id=uuid.uuid4(), started_at=started, trigger=trigger, status="completed"
    )
    session.add(run)

    # System-wide read: see every tenant's brands. No-op when RLS is disabled.
    try:
        from aicmo.db import rls as _rls

        await _rls.set_bypass(session, on=True)
    except Exception as e:
        log.warning("ops.cycle.rls_bypass_failed", error=str(e)[:120])

    brands = await _active_brands(session)
    details: list[BrandCycleResult] = []
    captured = 0
    events_total = 0
    errors = 0

    for brand_id, org_id in brands:
        try:
            # Grab the prior snapshot BEFORE capturing the new one so 4.2 can
            # compare current → previous.
            prev = await monitoring.latest_snapshot(session, brand_id=brand_id)
            did, reason, metrics = await monitoring.capture_brand_snapshot(
                session, organization_id=org_id, brand_id=brand_id, now=started
            )
            brand_events = 0
            if did:
                captured += 1
                if prev is not None:
                    evs = await events.detect_and_store(
                        session,
                        organization_id=org_id,
                        brand_id=brand_id,
                        current=metrics,
                        previous=dict(prev.metrics or {}),
                        now=started,
                    )
                    brand_events = len(evs)
                    events_total += brand_events
            details.append(
                BrandCycleResult(
                    brand_id=str(brand_id),
                    snapshot_captured=did,
                    reason=reason,
                    metrics_count=len(metrics),
                    events_detected=brand_events,
                )
            )
        except Exception as e:
            errors += 1
            log.warning(
                "ops.cycle.brand_failed", brand_id=str(brand_id), error=str(e)[:120]
            )
            details.append(
                BrandCycleResult(
                    brand_id=str(brand_id), snapshot_captured=False, reason="error"
                )
            )

    finished = datetime.now(UTC)
    run.finished_at = finished
    run.brands_scanned = len(brands)
    run.snapshots_captured = captured
    run.events_detected = events_total
    run.status = "partial" if errors else "completed"
    run.detail = {"errors": errors, "brands": len(brands)}
    await session.commit()

    log.info(
        "ops.cycle.ran",
        trigger=trigger,
        brands=len(brands),
        captured=captured,
        events=events_total,
        errors=errors,
    )
    return TickResult(
        run_id=str(run.id),
        trigger=trigger,
        status=run.status,
        brands_scanned=len(brands),
        snapshots_captured=captured,
        events_detected=events_total,
        duration_ms=int((finished - started).total_seconds() * 1000),
        detail=details,
    )
