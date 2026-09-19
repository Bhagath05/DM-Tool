"""Transactional email for auth flows — a port with a dev log adapter.

Production wiring (SMTP / a provider) is a deliberate, unwired manual-setup
step: swap in an `EmailSender` implementation and register it in
`get_email_sender`. The dev adapter writes the verification / reset LINK to the
structured log so local flows are testable end-to-end without an email
provider. It never logs passwords or session tokens — only the one-time link,
which is itself single-use and short-lived.
"""

from __future__ import annotations

from typing import Protocol

import structlog

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


_sender: EmailSender = LogEmailSender()


def get_email_sender() -> EmailSender:
    """Return the process-wide email sender. Overridable in tests."""
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    """Swap the sender (production wiring or a test double)."""
    global _sender
    _sender = sender
