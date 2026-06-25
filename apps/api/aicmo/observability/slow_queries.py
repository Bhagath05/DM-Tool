"""Slow-query observability (P1) — reads `pg_stat_statements`.

The extension (enabled by migration 0045 + the `shared_preload_libraries`
preload in infra/docker-compose.yml) accumulates per-statement execution
stats. `top_slow_queries()` surfaces the statements whose *mean* execution
time exceeds a threshold so the monitor cron can alert before a slow query
becomes an outage.

Two safety properties:
  * **No-op when the extension is missing.** If `pg_stat_statements` isn't
    installed (e.g. a managed DB without the preload), the reader returns
    `available=False` and the monitor degrades silently — it never raises.
  * **No PII.** `pg_stat_statements` stores *normalized* query text with
    literals replaced by `$1, $2, …`, so the reported text carries no row
    data. We additionally exclude the monitor's own probe statements.
"""

from __future__ import annotations

import time

import structlog

log = structlog.get_logger()

# Statements we never want to flag: the extension's own catalog reads and
# the health-check probe. Matched case-insensitively against the normalized
# query text.
_EXCLUDE_FRAGMENTS = ("pg_stat_statements", "pg_extension")


async def _extension_present(session) -> bool:
    from sqlalchemy import text  # noqa: PLC0415

    row = await session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
    )
    return row.first() is not None


async def top_slow_queries(
    *, threshold_ms: float, limit: int
) -> dict:
    """Return the slowest statements by mean execution time.

    Shape::

        {
          "ok": bool,            # True unless the read itself errored
          "available": bool,     # whether pg_stat_statements is installed
          "breached": [ {query, mean_ms, max_ms, calls}, ... ],  # mean >= threshold
          "scan_ms": float,
        }

    `breached` is the subset of the top-`limit` statements whose mean
    execution time is at or above `threshold_ms`. Empty list ⇒ nothing slow.
    """
    from sqlalchemy import text  # noqa: PLC0415

    from aicmo.db.session import SessionLocal  # noqa: PLC0415

    t0 = time.monotonic()
    try:
        async with SessionLocal() as session:
            if not await _extension_present(session):
                return {
                    "ok": True,
                    "available": False,
                    "breached": [],
                    "detail": "pg_stat_statements not installed",
                    "scan_ms": round((time.monotonic() - t0) * 1000, 1),
                }

            rows = await session.execute(
                text(
                    """
                    SELECT
                        query,
                        mean_exec_time AS mean_ms,
                        max_exec_time  AS max_ms,
                        calls
                    FROM pg_stat_statements
                    WHERE mean_exec_time >= :threshold
                    ORDER BY mean_exec_time DESC
                    LIMIT :limit
                    """
                ),
                {"threshold": threshold_ms, "limit": limit},
            )
            breached: list[dict] = []
            for r in rows.mappings():
                q = (r["query"] or "").strip()
                low = q.lower()
                if any(frag in low for frag in _EXCLUDE_FRAGMENTS):
                    continue
                breached.append(
                    {
                        "query": q[:300],
                        "mean_ms": round(float(r["mean_ms"]), 1),
                        "max_ms": round(float(r["max_ms"]), 1),
                        "calls": int(r["calls"]),
                    }
                )
        return {
            "ok": True,
            "available": True,
            "breached": breached,
            "scan_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001
        # Never let monitoring break the cron. A failed scan is logged but
        # reported as ok=False so the caller can decide.
        log.warning("slow_queries.scan_failed", error=str(exc)[:200])
        return {
            "ok": False,
            "available": False,
            "breached": [],
            "error": str(exc)[:200],
            "scan_ms": round((time.monotonic() - t0) * 1000, 1),
        }
