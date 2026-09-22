"""Transactional email for auth flows — a port with a dev log adapter and a
first-party self-hosted SMTP adapter.

Two adapters implement the same `EmailSender` port:

- `LogEmailSender` (dev/test): writes the verification / reset LINK to the
  structured log so local flows are testable without a mail server. It never
  logs passwords or session tokens — only the one-time link, which is itself
  single-use and short-lived. Not for production.
- `SelfHostedSMTPEmailSender`: composes the email and delivers it through DM
  Tool's OWN SMTP server (`aicmo.email.smtp`) — no third-party provider or SDK.
  It NEVER writes the link or token to the log.

`build_email_sender(settings)` selects between them purely from configuration:
the SMTP adapter is used ONLY when DM Tool's SMTP transport is configured
(`SMTP_HOST` + `SMTP_FROM`), so development and staging never accidentally send
real mail. The production boot guard (`config.validate_production_secrets`)
fails closed when SMTP is unconfigured or its TLS is unsafe, so a production
deploy can never silently drop verification mail.

Initialization happens at the FastAPI lifespan boundary (see `aicmo.main`), not
at import — so tests can inject their own `EmailSender` without it being
clobbered by app construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    from aicmo.config import Settings

log = structlog.get_logger()


class EmailSender(Protocol):
    async def send_verification(self, *, to: str, link: str) -> None: ...
    async def send_password_reset(self, *, to: str, link: str) -> None: ...


class LogEmailSender:
    """Dev/test adapter: emits the link to logs instead of sending mail.

    The link carries a single-use, short-lived token; logging it in dev is
    acceptable and is the intended local delivery channel. Do not use in
    production — the SMTP adapter is used there.
    """

    async def send_verification(self, *, to: str, link: str) -> None:
        log.info("auth.email.verification", to=to, link=link, delivery="log")

    async def send_password_reset(self, *, to: str, link: str) -> None:
        log.info("auth.email.password_reset", to=to, link=link, delivery="log")


def _verification_html(link: str, product: str) -> str:
    return (
        f"<p>Welcome to {product}.</p>"
        f"<p>Confirm your email address to activate your account:</p>"
        f'<p><a href="{link}">Verify my email</a></p>'
        f"<p>This link is single-use and expires soon. If you didn't create a "
        f"{product} account, you can safely ignore this email.</p>"
    )


def _password_reset_html(link: str, product: str) -> str:
    return (
        f"<p>We received a request to reset your {product} password.</p>"
        f'<p><a href="{link}">Reset my password</a></p>'
        f"<p>This link is single-use and expires soon. If you didn't request a "
        f"reset, you can safely ignore this email — your password won't change.</p>"
    )


class SelfHostedSMTPEmailSender:
    """Delivers auth verification / password-reset links through DM Tool's own
    SMTP server (`aicmo.email.smtp`). No third-party provider. NEVER logs the
    link or token — only a non-sensitive delivery event (recipient + kind)."""

    def __init__(self, *, product_name: str = "DM Tool") -> None:
        self._product = product_name

    async def _deliver(self, *, to: str, subject: str, html: str, kind: str) -> None:
        # Lazy imports keep auth decoupled from the config/email modules at
        # import time and avoid import cycles.
        from aicmo.config import get_settings
        from aicmo.email.smtp import SmtpDeliveryError, SmtpNotConfiguredError, send_email

        try:
            await send_email(get_settings(), to=to, subject=subject, html=html)
        except (SmtpNotConfiguredError, SmtpDeliveryError):
            # The link/token lives ONLY inside the message body handed to SMTP —
            # never in our logs. Record the failure without it. (Enumeration-safe:
            # the router still returns its generic response; ops alerts on this.)
            log.warning("auth.email.delivery_failed", kind=kind, to=to)
            return
        log.info("auth.email.sent", kind=kind, to=to)

    async def send_verification(self, *, to: str, link: str) -> None:
        await self._deliver(
            to=to,
            subject=f"Verify your {self._product} email",
            html=_verification_html(link, self._product),
            kind="verification",
        )

    async def send_password_reset(self, *, to: str, link: str) -> None:
        await self._deliver(
            to=to,
            subject=f"Reset your {self._product} password",
            html=_password_reset_html(link, self._product),
            kind="password_reset",
        )


def build_email_sender(settings: Settings) -> EmailSender:
    """Select the process email sender from configuration.

    The self-hosted SMTP adapter is used ONLY when DM Tool's SMTP transport is
    configured (`smtp_configured`); otherwise the dev `LogEmailSender`, so local
    and staging environments never accidentally send real mail. Called once at
    the FastAPI lifespan boundary — tests may still override via
    `set_email_sender`.
    """
    from aicmo.email.smtp import smtp_configured

    return SelfHostedSMTPEmailSender() if smtp_configured(settings) else LogEmailSender()


_sender: EmailSender = LogEmailSender()


def get_email_sender() -> EmailSender:
    """Return the process-wide email sender. Overridable in tests."""
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    """Swap the sender (lifespan wiring or a test double)."""
    global _sender
    _sender = sender
