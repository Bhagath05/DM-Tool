"""Transactional email for auth flows — a port with a dev log adapter and a
config-driven production adapter.

Two adapters implement the same `EmailSender` port:

- `LogEmailSender` (dev/test): writes the verification / reset LINK to the
  structured log so local flows are testable without an email provider. It
  never logs passwords or session tokens — only the one-time link, which is
  itself single-use and short-lived. Not for production.
- `ProductionEmailSender`: composes the email and delivers it through the one
  shared transactional provider (`aicmo.modules.crm.email_providers`, e.g.
  Resend over HTTPS). It NEVER writes the link or token to the log.

`build_email_sender(settings)` selects between them purely from configuration:
a real provider is used ONLY when `EMAIL_PROVIDER` (+ key + from) is fully set,
so development and staging never accidentally send real mail. The production
boot guard (`config.validate_production_secrets`) fails closed when email is
unconfigured, so a production deploy can never silently drop verification mail.
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
    production — register a real sender there.
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


class ProductionEmailSender:
    """Delivers auth verification / password-reset links through the shared
    transactional email provider. NEVER logs the link or token — only a
    non-sensitive delivery event (recipient + provider + status)."""

    def __init__(self, *, product_name: str = "DM Tool") -> None:
        self._product = product_name

    async def _deliver(self, *, to: str, subject: str, html: str, kind: str) -> None:
        # Lazy import keeps auth decoupled from the CRM module at import time and
        # avoids any import cycle (crm.email_providers imports only aicmo.config).
        from aicmo.modules.crm.email_providers import EmailSendRequest, get_email_provider

        result = await get_email_provider().send(
            EmailSendRequest(to_email=to, subject=subject, html=html)
        )
        # The link/token lives ONLY in the email body handed to the provider —
        # never in our logs. Record just the delivery outcome.
        if result.status == "failed":
            log.warning(
                "auth.email.delivery_failed", kind=kind, to=to, provider=result.provider
            )
        else:
            log.info(
                "auth.email.sent",
                kind=kind,
                to=to,
                provider=result.provider,
                status=result.status,
            )

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

    A real provider is used ONLY when fully configured
    (`email_delivery_configured`); otherwise the dev `LogEmailSender`, so local
    and staging environments never accidentally send real mail. Called once at
    startup (composition root) — tests may still override via `set_email_sender`.
    """
    from aicmo.config import email_delivery_configured

    return ProductionEmailSender() if email_delivery_configured(settings) else LogEmailSender()


_sender: EmailSender = LogEmailSender()


def get_email_sender() -> EmailSender:
    """Return the process-wide email sender. Overridable in tests."""
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    """Swap the sender (production wiring or a test double)."""
    global _sender
    _sender = sender
