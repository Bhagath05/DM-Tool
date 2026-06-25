"""P0-4 (alerts) + P0-5 (deep health) — observability."""

from __future__ import annotations

import asyncio

import pytest

from aicmo.config import get_settings
from aicmo.observability import alerts, health


# ---- P0-4: Slack alerting ----


def test_notify_slack_noop_when_unset(monkeypatch):
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "")
    get_settings.cache_clear()
    assert asyncio.run(alerts.notify_slack("hi")) is False
    get_settings.cache_clear()


def test_alert_never_raises(monkeypatch):
    # Even with a bogus webhook, alert() must swallow errors (best-effort).
    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "http://127.0.0.1:1/none")
    get_settings.cache_clear()
    asyncio.run(alerts.alert("boom", level="error", extra="x"))  # no raise
    asyncio.run(alerts.alert_job_failure("job_x", RuntimeError("kaboom")))  # no raise
    get_settings.cache_clear()


def test_notify_slack_posts_when_set(monkeypatch):
    sent = {}

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            sent["url"] = url
            sent["json"] = json
            return _Resp()

    import httpx

    monkeypatch.setenv("SLACK_ALERT_WEBHOOK_URL", "https://hooks.slack.test/x")
    get_settings.cache_clear()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    ok = asyncio.run(alerts.notify_slack("the message", level="warning"))
    assert ok is True
    assert sent["url"] == "https://hooks.slack.test/x"
    assert "the message" in sent["json"]["text"]
    get_settings.cache_clear()


# ---- P0-5: deep health ----


def test_readiness_reports_all_three_dependencies():
    async def fake_db():
        return {"ok": True, "latency_ms": 1.0}

    async def fake_redis():
        return {"ok": True, "latency_ms": 1.0}

    async def fake_queue():
        return {"ok": True, "detail": "worker heartbeat present"}

    import aicmo.observability.health as h

    h.check_db, h.check_redis, h.check_queue = fake_db, fake_redis, fake_queue  # type: ignore
    ok, report = asyncio.run(h.readiness())
    assert ok is True
    assert set(report.keys()) == {"database", "redis", "queue"}


def test_readiness_fails_when_db_down(monkeypatch):
    async def db_down():
        return {"ok": False, "error": "connection refused"}

    async def ok_redis():
        return {"ok": True}

    async def ok_queue():
        return {"ok": True}

    monkeypatch.setattr(health, "check_db", db_down)
    monkeypatch.setattr(health, "check_redis", ok_redis)
    monkeypatch.setattr(health, "check_queue", ok_queue)
    ok, report = asyncio.run(health.readiness())
    assert ok is False  # DB down → not ready (503)
    assert report["database"]["ok"] is False


def test_monitor_cron_alerts_on_failure(monkeypatch):
    async def degraded():
        return False, {"database": {"ok": False}, "redis": {"ok": True}, "queue": {"ok": True}}

    fired = {}

    async def fake_alert(message, **kw):
        fired["message"] = message

    monkeypatch.setattr(health, "readiness", degraded)
    monkeypatch.setattr("aicmo.observability.alerts.alert", fake_alert)
    asyncio.run(health.monitor_system_cron({}))
    assert "database" in fired.get("message", "")
