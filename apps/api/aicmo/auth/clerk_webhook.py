"""Phase 10.2c — Svix-style HMAC verification for Clerk webhooks.

Clerk uses Svix for webhook delivery. The signature scheme:

  signature = base64(HMAC_SHA256(secret_bytes, f"{msg_id}.{timestamp}.{body}"))

Where:
  - secret_bytes = base64-decoded portion of CLERK_WEBHOOK_SIGNING_SECRET
    (strip the `whsec_` prefix first)
  - msg_id     = the `svix-id` header (or `webhook-id`)
  - timestamp  = the `svix-timestamp` header (unix epoch seconds, string)
  - body       = the raw request body bytes (no re-serialisation)

The `svix-signature` header carries `v1,<sig> v1,<sig> ...` — multiple
candidate signatures, any one matching wins (Svix supports key rotation).

We implement this inline (no external dependency) for three reasons:
  1. The verification is ~20 lines — adding `svix` to deps is more
     surface area than the implementation it would replace.
  2. We can unit-test the bare HMAC math against known vectors without
     library mocking.
  3. Future webhook providers (Stripe, Slack) follow the same pattern;
     this gives us a template.

Replay defence: payloads older than `clerk_webhook_tolerance_seconds`
(default 300s) are rejected even if signed correctly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

import structlog

from aicmo.config import get_settings

log = structlog.get_logger()


class WebhookVerificationError(Exception):
    """Raised when a webhook payload fails verification.

    The router catches this and returns 400 — the same response Clerk
    expects for a malformed delivery. We deliberately do NOT vary the
    response by failure reason to avoid leaking which check failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    msg_id: str
    timestamp: int
    body: bytes


def _secret_bytes() -> bytes:
    """Decode the configured `whsec_<base64>` to raw bytes."""
    raw = get_settings().clerk_webhook_signing_secret.strip()
    if not raw:
        raise WebhookVerificationError("webhook_disabled")
    if raw.startswith("whsec_"):
        raw = raw[len("whsec_") :]
    try:
        return base64.b64decode(raw)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise WebhookVerificationError("malformed_secret") from exc


def _sign(secret: bytes, msg_id: str, timestamp: str, body: bytes) -> bytes:
    """Produce the base64'd HMAC-SHA256 — matches Svix's `v1` scheme."""
    payload = f"{msg_id}.{timestamp}.".encode("ascii") + body
    mac = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.b64encode(mac)


def verify(
    *,
    headers: dict[str, str],
    body: bytes,
    now: int | None = None,
) -> VerifiedWebhook:
    """Verify a webhook delivery. Raise WebhookVerificationError on any failure.

    Headers map is case-insensitive in HTTP but we lowercase explicitly
    here so callers can pass `dict(request.headers)` without ceremony.
    """
    h = {k.lower(): v for k, v in headers.items()}

    msg_id = h.get("svix-id") or h.get("webhook-id")
    timestamp = h.get("svix-timestamp") or h.get("webhook-timestamp")
    sig_header = h.get("svix-signature") or h.get("webhook-signature")
    if not (msg_id and timestamp and sig_header):
        raise WebhookVerificationError("missing_headers")

    # Replay defence — reject timestamps too far in the past or future.
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("bad_timestamp") from exc

    settings = get_settings()
    tolerance = max(1, int(settings.clerk_webhook_tolerance_seconds))
    current = int(now if now is not None else time.time())
    if abs(current - ts_int) > tolerance:
        raise WebhookVerificationError("timestamp_out_of_tolerance")

    secret = _secret_bytes()
    expected = _sign(secret, msg_id, timestamp, body)

    # `svix-signature` is space-delimited list of `<version>,<base64sig>`.
    # Any one matching wins (key rotation support).
    for candidate in sig_header.split():
        if "," not in candidate:
            continue
        version, sig_b64 = candidate.split(",", 1)
        if version != "v1":
            continue
        # constant-time compare against the bytes form so a short-circuit
        # length check can't be a side-channel.
        if hmac.compare_digest(sig_b64.encode("ascii"), expected):
            return VerifiedWebhook(
                msg_id=msg_id, timestamp=ts_int, body=body
            )

    raise WebhookVerificationError("signature_mismatch")


# ---------------------------------------------------------------------
#  Test helper — exported so tests can mint valid signatures without
#  duplicating the algorithm.
# ---------------------------------------------------------------------


def sign_for_testing(
    *,
    secret_whsec: str,
    msg_id: str,
    timestamp: int,
    body: bytes,
) -> str:
    """Produce a valid `svix-signature` header value for tests.

    NEVER call this from production code paths — the secret should
    only ever be loaded from config there.
    """
    raw = secret_whsec.strip()
    if raw.startswith("whsec_"):
        raw = raw[len("whsec_") :]
    secret = base64.b64decode(raw)
    sig = _sign(secret, msg_id, str(timestamp), body).decode("ascii")
    return f"v1,{sig}"
