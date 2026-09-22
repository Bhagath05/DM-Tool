"""First-party SMTP email transport.

DM Tool sends transactional mail by talking directly to an SMTP server it
controls — no third-party email provider or SDK. Pure standard library
(``smtplib`` + ``email.message``); the blocking send runs in a worker thread so
it never blocks the async event loop.

Security posture:
- TLS is required in production. Submission uses STARTTLS (``starttls``) or
  implicit TLS (``tls``). The only non-TLS mode (``none``) is reserved for a
  private, trusted network and the production boot guard rejects it; and in
  ANY environment an authenticated send (username/password) over ``none`` is
  refused, so credentials are never transmitted in cleartext. STARTTLS never
  silently downgrades — if the server can't upgrade, the send fails.
- Credentials come from settings/secrets only — never logged, never persisted,
  never returned to clients.
- Message bodies (which may carry one-time verification/reset links) are never
  written to the log here.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from aicmo.config import Settings

log = structlog.get_logger()

TLS_MODES: frozenset[str] = frozenset({"starttls", "tls", "none"})


class SmtpNotConfiguredError(RuntimeError):
    """SMTP is unusable as configured — host/sender missing, or a refused
    insecure configuration (e.g. authenticated send over a plaintext
    connection). Callers must not pretend to send."""


class SmtpDeliveryError(RuntimeError):
    """SMTP transport / handshake / auth / send failure."""


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    tls: str  # "starttls" | "tls" | "none"
    from_addr: str


def smtp_config_from_settings(settings: Settings) -> SmtpConfig | None:
    """Return a complete SmtpConfig, or None when host/sender are missing.

    Takes the settings object (rather than importing config) so it stays
    import-cycle free and unit-testable with a stub."""
    host = (getattr(settings, "smtp_host", "") or "").strip()
    from_addr = (getattr(settings, "smtp_from", "") or "").strip()
    if not host or not from_addr:
        return None
    return SmtpConfig(
        host=host,
        port=int(getattr(settings, "smtp_port", 587) or 587),
        username=(getattr(settings, "smtp_username", "") or "").strip(),
        password=getattr(settings, "smtp_password", "") or "",
        tls=(getattr(settings, "smtp_tls", "starttls") or "starttls").strip().lower(),
        from_addr=from_addr,
    )


def smtp_configured(settings: Settings) -> bool:
    """True iff DM Tool's own SMTP transport is configured (host + sender set)."""
    return smtp_config_from_settings(settings) is not None


def smtp_production_problems(settings: Settings) -> list[str]:
    """Production-readiness problems with the SMTP config (empty list = OK).

    Drives the boot guard so production fails closed rather than silently
    degrading to a log-only sender."""
    problems: list[str] = []
    cfg = smtp_config_from_settings(settings)
    if cfg is None:
        problems.append(
            "SMTP is not configured — set SMTP_HOST and SMTP_FROM for DM Tool's "
            "own mail server (verification/reset email won't be delivered otherwise)."
        )
        return problems
    if cfg.tls == "none":
        problems.append(
            "SMTP_TLS must not be 'none' in production — TLS is required so "
            "credentials and one-time links are never sent over plaintext."
        )
    elif cfg.tls not in TLS_MODES:
        problems.append(f"SMTP_TLS is invalid ({cfg.tls!r}); use 'starttls' or 'tls'.")
    if cfg.username and not cfg.password:
        problems.append("SMTP_USERNAME is set but SMTP_PASSWORD is missing.")
    return problems


def _build_message(cfg: SmtpConfig, *, to: str, subject: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = cfg.from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("Open this message in an HTML-capable email client.")
    msg.add_alternative(html, subtype="html")
    return msg


def _send_blocking(cfg: SmtpConfig, msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    if cfg.tls == "tls":
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=30) as client:
            if cfg.username:
                client.login(cfg.username, cfg.password)
            client.send_message(msg)
        return
    with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as client:
        client.ehlo()
        if cfg.tls == "starttls":
            # Fail closed: if the server can't STARTTLS, smtplib raises — we
            # never fall back to plaintext.
            client.starttls(context=context)
            client.ehlo()
        elif cfg.tls != "none":
            raise SmtpDeliveryError(f"Unknown SMTP TLS mode: {cfg.tls!r}")
        if cfg.username:
            client.login(cfg.username, cfg.password)
        client.send_message(msg)


async def send_email(settings: Settings, *, to: str, subject: str, html: str) -> None:
    """Deliver one message through DM Tool's SMTP server.

    Raises ``SmtpNotConfiguredError`` when SMTP isn't set up (callers must not claim a
    send), or ``SmtpDeliveryError`` on transport failure. Never logs the body,
    the one-time link, or the SMTP credentials."""
    cfg = smtp_config_from_settings(settings)
    if cfg is None:
        raise SmtpNotConfiguredError("SMTP is not configured (SMTP_HOST + SMTP_FROM required).")
    # Never transmit SMTP AUTH credentials over a plaintext connection. This
    # holds in EVERY environment — the production boot guard already rejects
    # tls=none, but non-prod has no such guard — so refuse here, before any
    # socket is opened, rather than logging in over cleartext.
    if cfg.tls == "none" and (cfg.username or cfg.password):
        raise SmtpNotConfiguredError(
            "Refusing authenticated SMTP over a plaintext connection: SMTP_TLS=none "
            "with SMTP_USERNAME/SMTP_PASSWORD set. Use SMTP_TLS='starttls' or 'tls', "
            "or clear the credentials for a trusted unauthenticated relay."
        )
    msg = _build_message(cfg, to=to, subject=subject, html=html)
    try:
        await asyncio.to_thread(_send_blocking, cfg, msg)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        # Failure event only — never the body/link or credentials.
        log.warning("email.smtp.delivery_failed", to=to, host=cfg.host, error=type(exc).__name__)
        raise SmtpDeliveryError(str(exc)) from exc
    log.info("email.smtp.sent", to=to, host=cfg.host)
