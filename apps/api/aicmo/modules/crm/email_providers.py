"""Email provider abstraction (Phase 6.5, Slice 4).

Same no-vendor-lock pattern as the image / video / storage providers: an
interface + a stub, selected via config. The stub RECORDS an email as queued
but does NOT deliver it — so the whole templates / sequences / tracking flow
runs end-to-end with NO external dependency and NO fabricated delivery. A real
provider (DM Tool's own SMTP server, `aicmo.email.smtp`) delivers when
configured; only then do emails actually leave the building. No third party.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

import structlog

from aicmo.config import get_settings

log = structlog.get_logger()


@dataclass(frozen=True)
class EmailSendRequest:
    to_email: str
    subject: str
    html: str
    from_email: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    message_id: str
    # "queued" = accepted for delivery by a real provider; "recorded" = stub
    # stored it but did NOT send (no credentials). Never claim delivered here —
    # delivery is confirmed only by a real provider webhook.
    status: str
    delivered: bool


class EmailProvider(Protocol):
    name: str

    async def send(self, request: EmailSendRequest) -> EmailSendResult: ...


class StubEmailProvider:
    name = "stub"

    async def send(self, request: EmailSendRequest) -> EmailSendResult:
        # Offline: record only. No email is actually delivered.
        log.info("email.stub.recorded", to=request.to_email)
        return EmailSendResult(
            provider="stub", message_id=f"stub-{uuid.uuid4().hex}",
            status="recorded", delivered=False,
        )


class SmtpEmailProvider:
    """Real delivery via DM Tool's OWN SMTP server (``aicmo.email.smtp``) — no
    third-party provider or SDK. Never fabricates delivery: a successful SMTP
    hand-off is reported as "queued" (final delivery is confirmed by a
    bounce/DSN, so ``delivered`` stays False here). Transport failures are
    logged (without body/credentials) and returned as status "failed" — the
    caller decides how to react; we never raise into a request path.
    """

    name = "smtp"

    async def send(self, request: EmailSendRequest) -> EmailSendResult:
        from aicmo.email.smtp import SmtpDeliveryError, SmtpNotConfiguredError, send_email

        try:
            await send_email(
                get_settings(),
                to=request.to_email,
                subject=request.subject,
                html=request.html,
            )
        except (SmtpNotConfiguredError, SmtpDeliveryError):
            # Failure event only — never the body, link, or credentials.
            log.warning("email.smtp.rejected", to=request.to_email)
            return EmailSendResult(
                provider=self.name, message_id="", status="failed", delivered=False
            )
        return EmailSendResult(
            provider=self.name, message_id="", status="queued", delivered=False
        )


def get_email_provider() -> EmailProvider:
    """DM Tool's self-hosted SMTP provider when configured; the record-only stub
    otherwise (dev/tests never need credentials and nothing is fabricated as
    delivered)."""
    from aicmo.email.smtp import smtp_configured

    return SmtpEmailProvider() if smtp_configured(get_settings()) else StubEmailProvider()
