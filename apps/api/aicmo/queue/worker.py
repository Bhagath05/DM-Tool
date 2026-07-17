"""Arq worker settings.

Run with:  pnpm --filter @ai-cmo/api worker
Or:        uv run arq aicmo.queue.worker.WorkerSettings
"""

from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from aicmo.config import get_settings

_settings = get_settings()


def _redis_settings_from_url(url: str) -> RedisSettings:
    # arq expects a host/port object; build one from the URL.
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
        password=parsed.password,
    )


async def startup(ctx: dict) -> None:
    ctx["env"] = _settings.api_env
    # P0-4: the worker is a separate process from the API and must init Sentry
    # itself, or job exceptions would never reach Sentry. No-op without a DSN.
    try:
        from aicmo.observability.sentry import init_sentry

        init_sentry()
    except Exception:
        pass


async def shutdown(ctx: dict) -> None:
    pass


# Central job registry. Every feature module that adds a `tasks.py`
# appends its `@tenant_job`-decorated functions here so the worker
# discovers them. Phase 0 ships only the reference job.
from aicmo.modules.advisor.tasks import evaluate_advisor_outcomes  # noqa: E402
from aicmo.modules.operations.tasks import operations_cycle_cron  # noqa: E402
from aicmo.modules.publishing.tasks import (  # noqa: E402
    publish_due_cron,
    publish_due_scheduled_posts,
)
from aicmo.modules.video.tasks import generate_video_stub, render_design_video  # noqa: E402
from aicmo.observability.health import monitor_system_cron  # noqa: E402
from aicmo.queue.reference import echo_tenant_job  # noqa: E402

ALL_JOBS: list = [
    echo_tenant_job,
    generate_video_stub,
    render_design_video,
    evaluate_advisor_outcomes,
    publish_due_scheduled_posts,
]

# P0-3 + P0-4: time-driven jobs. `run_at_startup=False`; arq fires them at the
# configured cron times. `second=0` → once per minute.
CRON_JOBS: list = [
    cron(publish_due_cron, second=0, run_at_startup=False),
    cron(monitor_system_cron, second=0, run_at_startup=False),
    # Phase 8 — the AI employee's daily shift. Once a day at the configured
    # hour; reuses run_operations_cycle (same function /operations/tick calls).
    # Guarded by an emergency stop + the existing master switches.
    cron(
        operations_cycle_cron,
        hour=_settings.operations_daily_cron_hour,
        minute=0,
        second=0,
        run_at_startup=False,
    ),
]


class WorkerSettings:
    """Arq worker entrypoint. Job functions live in `ALL_JOBS`, populated
    by feature modules' `tasks.py` (see modules/<name>/tasks.py and the
    reference template in queue/reference.py). Time-driven jobs live in
    `CRON_JOBS`."""

    redis_settings = _redis_settings_from_url(_settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    functions = ALL_JOBS
    cron_jobs = CRON_JOBS
    # P0-5: write the `arq:health-check` heartbeat key every 30s so the API's
    # /readyz queue-validation can detect a live worker.
    health_check_interval = 30
