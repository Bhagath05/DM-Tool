"""Deep health checks (P0-5) + the system-monitor cron (P0-4 DB/Redis alerts).

`readiness()` validates the three runtime dependencies — PostgreSQL, Redis,
and the job queue — and is what the `/readyz` endpoint and the monitor cron
both call. The shallow `/health` (liveness) stays as-is.
"""

from __future__ import annotations

import time

import structlog

log = structlog.get_logger()


async def check_db() -> dict:
    """PostgreSQL: a real round-trip (`SELECT 1`)."""
    from sqlalchemy import text  # noqa: PLC0415

    from aicmo.db.session import SessionLocal  # noqa: PLC0415

    t0 = time.monotonic()
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


async def _redis_client():
    import redis.asyncio as redis  # noqa: PLC0415

    from aicmo.config import get_settings  # noqa: PLC0415

    return redis.from_url(get_settings().redis_url)


async def check_redis() -> dict:
    """Redis: a real PING."""
    t0 = time.monotonic()
    client = None
    try:
        client = await _redis_client()
        await client.ping()
        return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


async def check_queue() -> dict:
    """Job queue: look for the Arq worker heartbeat key. The worker writes
    `arq:health-check` every `health_check_interval`; its absence means no
    worker is consuming jobs."""
    client = None
    try:
        client = await _redis_client()
        val = await client.get("arq:health-check")
        return {
            "ok": val is not None,
            "detail": "worker heartbeat present" if val else "no recent worker heartbeat",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


async def readiness() -> tuple[bool, dict]:
    """Return (overall_ok, per-dependency report).

    `overall_ok` requires DB + Redis (the API's hard dependencies). The queue
    heartbeat is reported but does NOT fail API readiness — the API can serve
    requests while the worker is restarting; a missing worker is surfaced
    separately by the monitor + the `queue` field."""
    db = await check_db()
    rd = await check_redis()
    q = await check_queue()
    overall = bool(db["ok"] and rd["ok"])
    return overall, {"database": db, "redis": rd, "queue": q}


async def monitor_system_cron(ctx: dict) -> dict:
    """Every-minute cron: alert on DB/Redis/worker-queue failure (P0-4) and on
    slow queries surfaced by pg_stat_statements (P1)."""
    from aicmo.observability.alerts import alert  # noqa: PLC0415

    ok, report = await readiness()
    degraded = [k for k, v in report.items() if isinstance(v, dict) and not v.get("ok")]
    if degraded:
        await alert(
            f"Health check degraded: {', '.join(degraded)}",
            level="error" if not ok else "warning",
            report=report,
        )

    # P1 — slow-query scan. Best-effort: degrades silently if the extension
    # isn't installed, and never fails the health report.
    slow = await _scan_slow_queries()
    report["slow_queries"] = slow
    if slow.get("breached"):
        worst = slow["breached"][0]
        await alert(
            f"{len(slow['breached'])} slow queries (slowest mean "
            f"{worst['mean_ms']}ms over {worst['calls']} calls)",
            level="warning",
            slow_queries=slow["breached"],
        )

    return report


async def _scan_slow_queries() -> dict:
    """Read the slow-query threshold from settings and scan pg_stat_statements."""
    from aicmo.config import get_settings  # noqa: PLC0415
    from aicmo.observability.slow_queries import top_slow_queries  # noqa: PLC0415

    settings = get_settings()
    return await top_slow_queries(
        threshold_ms=settings.slow_query_alert_ms,
        limit=settings.slow_query_top_n,
    )
