"""Email provider abstraction (Phase 6.5, Slice 4).

Same no-vendor-lock pattern as the image / video / storage providers: an
interface + a stub, selected via config. The stub RECORDS an email as queued
but does NOT deliver it — so the whole templates / sequences / tracking flow
runs end-to-end with NO external dependency and NO fabricated delivery. A real
provider (SMTP / SendGrid / SES / Resend) drops in later by implementing the
same protocol; only then do emails actually leave the building.
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


def get_email_provider() -> EmailProvider:
    """Real provider when configured; the record-only stub otherwise (dev/tests
    never need credentials and nothing is ever fabricated as delivered)."""
    settings = get_settings()
    # A real provider is wired here once `email_provider` + credentials exist in
    # settings. Until then we honestly return the stub.
    if getattr(settings, "email_provider", "") and getattr(settings, "email_provider", "") != "stub":
        log.warning("email.provider.unconfigured", requested=settings.email_provider)
    return StubEmailProvider()
