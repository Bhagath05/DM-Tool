"""Phase 8 — daily autonomous execution (Priority 4).

Drives the EXISTING operations cycle once a day on the EXISTING Arq worker.

Deliberately thin: no new scheduler, no new worker, no new reasoning. This is
a guarded entry point that calls `run_operations_cycle()` — the same function
`POST /operations/tick` already calls. The whole lifecycle (observe → detect →
decide → propose policy-gated work), its per-brand cadence, its throttle and
its `OperationsRun` audit row all already exist and are reused as-is.

Safety, in order of precedence:
  1. `operations_emergency_stop`  — hard kill switch, checked first.
  2. `operations_daily_cron_enabled` — turns the schedule off.
  3. `operations_pipeline_enabled` / `autonomy_execution_enabled` — the
     existing master switches inside the pipeline. While they're off the cycle
     still only observes/detects; nothing reasons, spends or executes.
  4. The Autonomy Policy still gates every proposed action, so work lands as
     `awaiting_approval`. Nothing is ever published automatically.

Never raises: a worker cron that throws would take the whole worker's cron
loop down with it.
"""

from __future__ import annotations

import structlog

from aicmo.config import get_settings
from aicmo.db.session import SessionLocal
from aicmo.modules.operations.driver import run_operations_cycle

log = structlog.get_logger()


async def operations_cycle_cron(ctx: dict) -> dict:
    """Once-a-day driver for the autonomous cycle. Returns a small dict for
    the arq job record; every number here comes from the existing TickResult."""
    settings = get_settings()

    if settings.operations_emergency_stop:
        log.warning("ops.cron.emergency_stop_engaged")
        return {"status": "emergency_stopped", "note": "Emergency stop is on."}

    if not settings.operations_daily_cron_enabled:
        return {"status": "disabled", "note": "Daily execution is switched off."}

    try:
        async with SessionLocal() as session:
            result = await run_operations_cycle(session, trigger="cron")
            await session.commit()
    except Exception as e:
        log.warning("ops.cron.failed", error=str(e)[:200])
        return {"status": "failed", "note": "Cycle failed; will retry tomorrow."}

    log.info(
        "ops.cron.completed",
        status=result.status,
        brands_scanned=result.brands_scanned,
        events_detected=result.events_detected,
        work_scheduled=result.work_scheduled,
        duration_ms=result.duration_ms,
        pipeline_enabled=settings.operations_pipeline_enabled,
    )
    return {
        "status": result.status,
        "brands_scanned": result.brands_scanned,
        "snapshots_captured": result.snapshots_captured,
        "events_detected": result.events_detected,
        "work_scheduled": result.work_scheduled,
        "duration_ms": result.duration_ms,
    }
