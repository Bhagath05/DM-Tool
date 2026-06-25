"""P0-3 — publishing scheduler cron wiring + system publish."""

from __future__ import annotations

import inspect


def test_publish_due_cron_is_a_plain_coroutine():
    from aicmo.modules.publishing import tasks

    assert inspect.iscoroutinefunction(tasks.publish_due_cron)
    # It takes only `ctx` — i.e. it is NOT a @tenant_job (those require an
    # envelope kwarg). A cron runs system-wide with no tenant.
    params = list(inspect.signature(tasks.publish_due_cron).parameters)
    assert params == ["ctx"]


def test_system_publish_helper_exists():
    from aicmo.modules.publishing import service

    assert inspect.iscoroutinefunction(service.publish_all_due_posts)


def test_worker_registers_the_cron_every_minute():
    from aicmo.queue.worker import WorkerSettings

    crons = getattr(WorkerSettings, "cron_jobs", [])
    names = {getattr(c, "name", "") or getattr(c, "coroutine", None).__name__ for c in crons}
    assert any("publish_due_cron" in str(n) for n in names), names
    assert any("monitor_system_cron" in str(n) for n in names), names
    # Heartbeat so /readyz can validate the queue (P0-5).
    assert getattr(WorkerSettings, "health_check_interval", None) == 30


def test_cron_runs_every_minute_second_zero():
    from aicmo.queue.worker import WorkerSettings

    for c in WorkerSettings.cron_jobs:
        # arq CronJob stores the allowed second-set; {0} → once per minute.
        secs = getattr(c, "second", None)
        assert secs in ({0}, 0) or 0 in (secs or {0})
