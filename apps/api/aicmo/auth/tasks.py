"""ARQ worker job: resilient transactional auth-email delivery.

`send_auth_email` runs OFF the HTTP request path. It resolves the recipient from
the database (the payload carries only ``user_id`` + ``purpose`` — never a token,
URL, email address, or SMTP credential), mints a fresh single-use token, and
sends via DM Tool's own SMTP transport.

This is a SYSTEM job, not a tenant job: auth email happens pre-tenant (signup)
or unauthenticated (password reset), so it deliberately does not use
`@tenant_job` and opens its own session.

Retry policy (bounded): transient SMTP failures (connection/timeout/4xx) and a
not-yet-visible user row (the enqueuing signup may not have committed) are
retried with exponential backoff up to `AUTH_EMAIL_MAX_TRIES`. Permanent
failures (auth, TLS, 5xx, unconfigured SMTP) are NOT retried — they are logged
and handed to the bounce/suppression extension point. Nothing here logs a token,
a link, an email address, or an SMTP credential.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from arq import Retry

from aicmo.auth.email import build_email_sender
from aicmo.auth.email_delivery import (
    AUTH_EMAIL_MAX_TRIES,
    AUTH_EMAIL_PURPOSES,
    _issue_and_send,
    backoff_seconds,
    note_permanent_auth_email_failure,
)
from aicmo.config import get_settings
from aicmo.db.session import SessionLocal
from aicmo.email.smtp import SmtpDeliveryError, SmtpNotConfiguredError

log = structlog.get_logger()


async def send_auth_email(ctx: dict[str, Any], user_id: str, purpose: str) -> None:
    """Deliver one auth email, with bounded retries on transient failure.

    Enqueued via ``deliver_auth_email``; the ARQ payload carries only the
    internal ``user_id`` + ``purpose``."""
    job_id = ctx.get("job_id")
    job_try = int(ctx.get("job_try", 1))
    max_tries = int(ctx.get("max_tries") or AUTH_EMAIL_MAX_TRIES)
    settings = get_settings()

    def _log(outcome: str, classification: str | None = None, *, retry_scheduled: bool, **extra: Any):
        log.warning(
            "auth.email.job",
            email_type=purpose,
            job_id=job_id,
            attempt=job_try,
            outcome=outcome,
            classification=classification,
            retry_scheduled=retry_scheduled,
            **extra,
        )

    if purpose not in AUTH_EMAIL_PURPOSES:
        _log("dropped", "invalid_purpose", retry_scheduled=False)
        return
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        _log("dropped", "invalid_user_id", retry_scheduled=False)
        return

    # A raising SMTP sender so transport failures reach this worker for
    # classification; LogEmailSender (dev / SMTP unconfigured) never fails.
    sender = build_email_sender(settings, raising=True)

    try:
        async with SessionLocal() as session:
            sent = await _issue_and_send(
                session, user_id=uid, purpose=purpose, settings=settings, sender=sender
            )
            if not sent:
                # User row not visible yet — most likely the enqueuing signup
                # hasn't committed. Retry (bounded); if still absent, the signup
                # rolled back → give up without an email.
                await session.rollback()
                if job_try < max_tries:
                    delay = backoff_seconds(job_try)
                    _log("retry", "user_not_visible", retry_scheduled=True, retry_delay_seconds=delay)
                    raise Retry(defer=delay)
                _log("failed", "user_missing", retry_scheduled=False)
                return
            await session.commit()
    except Retry:
        raise
    except SmtpNotConfiguredError:
        _log("failed", "permanent_not_configured", retry_scheduled=False)
        await note_permanent_auth_email_failure(
            purpose=purpose, user_id=user_id, classification="not_configured",
            job_id=job_id, attempt=job_try,
        )
        return
    except SmtpDeliveryError as exc:
        transient = getattr(exc, "transient", True)
        if transient and job_try < max_tries:
            delay = backoff_seconds(job_try)
            _log("retry", "transient", retry_scheduled=True, retry_delay_seconds=delay)
            raise Retry(defer=delay) from None
        # Distinguish a bad DESTINATION (recipient rejected → suppress) from a
        # permanent OUR-side failure (auth/TLS/config → alert only) and from an
        # exhausted transient budget (address may still recover → alert only).
        recipient_rejected = not transient and getattr(exc, "recipient_rejected", False)
        if transient:
            classification = "transient_exhausted"
        elif recipient_rejected:
            classification = "recipient_rejected"
        else:
            classification = "permanent"
        _log("failed", classification, retry_scheduled=False)
        await note_permanent_auth_email_failure(
            purpose=purpose, user_id=user_id, classification=classification,
            job_id=job_id, attempt=job_try, recipient_rejected=recipient_rejected,
        )
        return

    log.info(
        "auth.email.job",
        email_type=purpose,
        job_id=job_id,
        attempt=job_try,
        outcome="sent",
        retry_scheduled=False,
    )
