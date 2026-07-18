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


class ResendEmailProvider:
    """Real delivery via Resend's HTTPS API (https://resend.com).

    HTTP-only (reuses httpx — no new dependency, no vendor SDK lock). Any
    Resend-compatible endpoint works via `email_api_base`. Never fabricates
    delivery: a 2xx means Resend *accepted* the message (status "queued");
    actual delivery is confirmed by the provider webhook, so `delivered` stays
    False here. Failures are logged and returned as status "failed" — the
    caller decides how to react; we never raise into a request path.
    """

    name = "resend"
    _ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from = from_email

    async def send(self, request: EmailSendRequest) -> EmailSendResult:
        import httpx

        payload = {
            "from": request.from_email or self._from,
            "to": [request.to_email],
            "subject": request.subject,
            "html": request.html,
        }
        if request.headers:
            payload["headers"] = request.headers
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    self._ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as e:
            log.warning("email.resend.transport_error", to=request.to_email, error=str(e)[:200])
            return EmailSendResult(
                provider=self.name, message_id="", status="failed", delivered=False
            )

        if resp.status_code >= 300:
            log.warning(
                "email.resend.rejected",
                to=request.to_email,
                status=resp.status_code,
                body=resp.text[:300],
            )
            return EmailSendResult(
                provider=self.name, message_id="", status="failed", delivered=False
            )

        message_id = ""
        try:
            message_id = (resp.json() or {}).get("id", "") or ""
        except Exception:
            pass
        log.info("email.resend.queued", to=request.to_email, message_id=message_id)
        return EmailSendResult(
            provider=self.name, message_id=message_id, status="queued", delivered=False
        )


def get_email_provider() -> EmailProvider:
    """Real provider when configured; the record-only stub otherwise (dev/tests
    never need credentials and nothing is ever fabricated as delivered)."""
    settings = get_settings()
    provider = (getattr(settings, "email_provider", "") or "").strip().lower()
    if provider == "resend":
        api_key = (getattr(settings, "email_api_key", "") or "").strip()
        from_email = (getattr(settings, "email_from", "") or "").strip()
        if api_key and from_email:
            return ResendEmailProvider(api_key=api_key, from_email=from_email)
        # Selected but not fully configured — honestly fall back, don't pretend.
        log.warning("email.provider.incomplete", requested=provider)
    elif provider and provider != "stub":
        log.warning("email.provider.unsupported", requested=provider)
    return StubEmailProvider()
