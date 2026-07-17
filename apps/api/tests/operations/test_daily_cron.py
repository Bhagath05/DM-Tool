"""Phase 8 Priority 4 — the AI employee's daily shift.

Pins that the daily cycle is driven by the EXISTING Arq worker (no second
scheduler), fires once a day at the configured hour, and that the safety
switches short-circuit BEFORE any DB/LLM work happens.
"""

from __future__ import annotations

import inspect

import pytest

from aicmo.config import get_settings
from aicmo.modules.operations import tasks
from aicmo.queue.worker import WorkerSettings


def _cron_names() -> list[str]:
    return [
        getattr(c, "name", "") or c.coroutine.__name__
        for c in WorkerSettings.cron_jobs
    ]


class TestWiring:
    def test_cron_is_a_plain_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(tasks.operations_cycle_cron)
        # arq crons take only ctx — no tenant envelope (runs system-wide).
        assert list(inspect.signature(tasks.operations_cycle_cron).parameters) == ["ctx"]

    def test_registered_on_the_existing_worker(self) -> None:
        assert any("operations_cycle_cron" in n for n in _cron_names()), _cron_names()

    def test_does_not_replace_the_existing_crons(self) -> None:
        names = _cron_names()
        assert any("publish_due_cron" in n for n in names)
        assert any("monitor_system_cron" in n for n in names)

    def test_runs_once_a_day_at_the_configured_hour(self) -> None:
        job = next(
            c
            for c in WorkerSettings.cron_jobs
            if "operations_cycle_cron" in (getattr(c, "name", "") or c.coroutine.__name__)
        )
        hour = get_settings().operations_daily_cron_hour
        # A daily job pins hour+minute+second. `hour` being set (not None) is
        # what makes this once-a-day rather than hourly — the owner's cadence.
        assert job.hour == hour, job.hour
        assert job.minute == 0
        assert job.second == 0
        assert job.run_at_startup is False


class TestSafetySwitches:
    @pytest.mark.asyncio
    async def test_emergency_stop_short_circuits_before_any_work(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*a, **k):  # must never be reached
            raise AssertionError("emergency stop must halt before the cycle runs")

        monkeypatch.setattr(tasks, "run_operations_cycle", _boom)
        monkeypatch.setattr(
            tasks, "get_settings", lambda: _S(emergency=True)
        )
        out = await tasks.operations_cycle_cron({})
        assert out["status"] == "emergency_stopped"

    @pytest.mark.asyncio
    async def test_disabled_flag_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*a, **k):
            raise AssertionError("disabled cron must not run the cycle")

        monkeypatch.setattr(tasks, "run_operations_cycle", _boom)
        monkeypatch.setattr(tasks, "get_settings", lambda: _S(enabled=False))
        out = await tasks.operations_cycle_cron({})
        assert out["status"] == "disabled"


class _S:
    """Minimal settings stub — only what the cron reads."""

    def __init__(self, *, emergency: bool = False, enabled: bool = True) -> None:
        self.operations_emergency_stop = emergency
        self.operations_daily_cron_enabled = enabled
        self.operations_pipeline_enabled = False


class TestDefaultsMatchThePolicy:
    def test_owner_configured_ceilings(self) -> None:
        s = get_settings()
        assert s.operations_daily_cron_hour == 8
        assert s.operations_daily_budget_usd == 1.0
        assert s.operations_max_tasks_per_cycle == 10
        assert s.operations_max_reasoning_tasks == 5
        assert s.operations_max_content_tasks == 5

    def test_spending_switches_are_off_by_default(self) -> None:
        """Nothing may reason/spend until someone deliberately turns it on."""
        s = get_settings()
        assert s.operations_pipeline_enabled is False
        assert s.autonomy_execution_enabled is False
        assert s.operations_emergency_stop is False
