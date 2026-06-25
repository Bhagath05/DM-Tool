"""Operational alerting (P0-4) — Slack webhook + Sentry.

Best-effort and non-blocking: an alert failure NEVER propagates into the
caller's path. Slack is a no-op when `SLACK_ALERT_WEBHOOK_URL` is unset, so
dev/test stay quiet; Sentry is a no-op when `SENTRY_DSN` is unset.
"""

from __future__ import annotations

import structlog

from aicmo.config import get_settings

log = structlog.get_logger()

_EMOJI = {"error": ":rotating_light:", "warning": ":warning:", "info": ":information_source:"}


async def notify_slack(text: str, *, level: str = "error") -> bool:
    """Post a message to the Slack alert webhook. Returns False (no raise)
    when unset or on any error."""
    settings = get_settings()
    url = getattr(settings, "slack_alert_webhook_url", "").strip()
    if not url:
        return False
    payload = {"text": f"{_EMOJI.get(level, ':bell:')} *DM Tool [{settings.api_env}]* — {text}"}
    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
        return resp.status_code < 300
    except Exception as exc:  # noqa: BLE001
        log.warning("alerts.slack_failed", error=str(exc)[:160])
        return False


def _sentry_message(message: str, *, level: str, **extra) -> None:
    try:
        import sentry_sdk  # noqa: PLC0415

        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=level)
    except Exception:  # noqa: BLE001
        pass


def _sentry_exception(exc: BaseException) -> None:
    try:
        import sentry_sdk  # noqa: PLC0415

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass


async def alert(message: str, *, level: str = "error", **context) -> None:
    """Fire-and-forget alert to logs + Sentry + Slack. Never raises."""
    (log.error if level == "error" else log.warning)("alert", message=message, **context)
    _sentry_message(message, level=level, **context)
    await notify_slack(message, level=level)


async def alert_job_failure(job: str, exc: BaseException) -> None:
    """A background job raised. Capture to Sentry + Slack. Never raises."""
    log.error("jobs.alert", job=job, error=str(exc)[:300])
    _sentry_exception(exc)
    await notify_slack(f"Background job `{job}` failed: {str(exc)[:300]}", level="error")
