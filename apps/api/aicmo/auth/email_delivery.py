"""Resilient delivery of transactional auth email.

Auth verification / password-reset mail is delivered OUT of the HTTP request
path through the existing ARQ worker, with bounded retries. This module holds
the pieces shared by the request side and the worker side:

- ``deliver_auth_email`` — the orchestration a request handler calls. When the
  ARQ pool is available it ENQUEUES a system job (the worker mints the token and
  sends); otherwise (dev, jobs disabled, or Redis unavailable) it falls back to
  synchronous best-effort delivery, preserving the original behavior.
- ``_issue_and_send`` — the single, shared send core used by BOTH paths, so the
  security properties are identical regardless of where it runs.

Security posture:
- The Redis job payload carries ONLY the internal ``user_id`` + ``purpose`` —
  never a token, a reset/verification URL, an email address, or SMTP creds. The
  recipient address is resolved from the database inside the worker, so a queued
  job can never be abused to mail an arbitrary address (the only enqueue sites
  are server-side auth workflows).
- The verification/reset token is CSPRNG-generated and only its hash is stored
  (``email_tokens.issue_token``); it is single-use and expiry-bound. Issuing a
  fresh token invalidates the user's prior unspent tokens of the same purpose,
  so a retry that re-issues never leaves two live tokens — retries cannot create
  inconsistent auth state.
- Nothing here logs a token, a link, an email address, or an SMTP credential.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

from aicmo.auth import email_tokens
from aicmo.auth.email import EmailSender, get_email_sender
from aicmo.modules.users.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.config import Settings

log = structlog.get_logger()

# The ARQ function name the worker registers (see aicmo/auth/tasks.py).
AUTH_EMAIL_JOB = "send_auth_email"
# The only purposes this path handles — mirrors the email_tokens CHECK constraint.
AUTH_EMAIL_PURPOSES: frozenset[str] = frozenset({"verify", "reset"})

# Bounded retry policy for transient SMTP failures. Exponential backoff, base
# 30s doubling, capped at 15 min; at most 5 attempts total.
AUTH_EMAIL_MAX_TRIES = 5
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_CAP_SECONDS = 900


def backoff_seconds(attempt: int) -> int:
    """Exponential backoff for retry ``attempt`` (1-based): 30, 60, 120, … cap 900."""
    exp = max(0, attempt - 1)
    return min(_BACKOFF_BASE_SECONDS * (2**exp), _BACKOFF_CAP_SECONDS)


def _verify_link(settings: Settings, raw_token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/verify-email?token={raw_token}"


def _reset_link(settings: Settings, raw_token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/reset-password?token={raw_token}"


async def _issue_and_send(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: str,
    settings: Settings,
    sender: EmailSender,
) -> bool:
    """Mint a token for ``user_id`` and send the matching auth email.

    Returns False when the user no longer exists (caller decides whether that is
    a transient not-yet-committed race or a permanent miss). The recipient is
    read from the user row — never supplied by a caller — and the raw token
    lives only inside the emailed link, never in a return value or a log."""
    if purpose not in AUTH_EMAIL_PURPOSES:
        raise ValueError(f"unknown auth email purpose: {purpose!r}")
    user = await session.get(User, user_id)
    if user is None:
        return False
    ttl = (
        settings.email_verify_ttl_seconds
        if purpose == "verify"
        else settings.password_reset_ttl_seconds
    )
    raw = await email_tokens.issue_token(
        session, user_id=user_id, purpose=purpose, ttl_seconds=ttl
    )
    if purpose == "verify":
        await sender.send_verification(to=user.email, link=_verify_link(settings, raw))
    else:
        await sender.send_password_reset(to=user.email, link=_reset_link(settings, raw))
    return True


async def deliver_auth_email(
    session: AsyncSession,
    pool: Any | None,
    *,
    user_id: uuid.UUID,
    purpose: str,
    settings: Settings,
) -> None:
    """Deliver an auth email, off the request path when possible.

    With an ARQ pool (and jobs enabled) this enqueues a system job carrying only
    ``user_id`` + ``purpose``; the worker resolves the recipient and mints the
    token. Without a pool it falls back to synchronous delivery so development
    (and any queue outage) still sends. Best-effort and never raises the HTTP
    response into an enumeration signal: enqueue failures degrade to the sync
    path rather than surfacing."""
    if purpose not in AUTH_EMAIL_PURPOSES:
        raise ValueError(f"unknown auth email purpose: {purpose!r}")

    if settings.jobs_enabled and pool is not None:
        try:
            await pool.enqueue_job(AUTH_EMAIL_JOB, str(user_id), purpose)
            # NO token, link, or email address — only the non-sensitive kind.
            log.info("auth.email.enqueued", email_type=purpose)
            return
        except Exception:
            # Redis hiccup: fall back to synchronous best-effort delivery so the
            # email still goes out. (The failure itself, not the payload.)
            log.warning("auth.email.enqueue_failed_sync_fallback", email_type=purpose)

    await _issue_and_send(
        session, user_id=user_id, purpose=purpose, settings=settings, sender=get_email_sender()
    )


async def note_permanent_auth_email_failure(
    *,
    purpose: str,
    user_id: str,
    classification: str,
    job_id: str | None = None,
    attempt: int | None = None,
) -> None:
    """Terminal auth-email delivery failure funnel: structured log + the shared
    operational alert, and the bounce/suppression extension point.

    Called EXACTLY once per terminal job state — a permanent failure (malformed
    recipient, 5xx rejection, unconfigured SMTP) or an exhausted retry budget —
    never per retry attempt, so a single ops alert fires with no duplicates. The
    ``user_id`` stays in the structured log (where a future suppression list will
    read it) but is deliberately kept OUT of the alert payload, which carries
    only safe operational context. Never logs/alerts a token, link, email
    address, or SMTP credential. Alerting is best-effort: any failure in the
    alert path is swallowed here so it can never affect auth/delivery."""
    try:
        # user_id lands in the log for the future bounce/suppression hook; it is
        # NOT forwarded to the alert (no unnecessary identifier in the alert).
        log.warning(
            "auth.email.permanent_failure",
            email_type=purpose,
            user_id=user_id,
            classification=classification,
            job_id=job_id,
            attempt=attempt,
        )
        # Reuse the existing operational alert path (logs + Sentry + Slack).
        from aicmo.observability.alerts import alert

        await alert(
            "Auth email delivery failed permanently",
            level="error",
            event="auth.email.permanent_failure",
            email_type=purpose,
            job_id=job_id,
            attempt=attempt,
            classification=classification,
        )
    except Exception:  # alerting must never affect the caller
        log.warning(
            "auth.email.alert_emit_failed",
            email_type=purpose,
            classification=classification,
        )
