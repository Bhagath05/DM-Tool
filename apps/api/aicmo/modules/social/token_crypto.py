"""Encrypt social OAuth tokens at rest.

Wraps `integrations.crypto` (Fernet) with two guarantees the publishing
pipeline needs:

  * `seal()`   — encrypt before write. When no key is configured (dev only)
                 it returns the plaintext and logs a warning, so local dev
                 keeps working; production REQUIRES the key (enforced in
                 `validate_production_secrets`), so prod always encrypts.
  * `unseal()` — decrypt on read, but transparently passes through legacy
                 PLAINTEXT values (rows written before this change) so the
                 migration can be rolled out without downtime.

Fernet tokens always begin with the version byte `\x80` → base64 prefix
`gAAAAA`. We use that to tell ciphertext from legacy plaintext, which makes
both `seal` and the back-fill script idempotent.
"""

from __future__ import annotations

import structlog

from aicmo.config import get_settings
from aicmo.modules.integrations import crypto

log = structlog.get_logger()

_FERNET_PREFIX = "gAAAAA"


def _key_present() -> bool:
    return bool(get_settings().integration_token_key.strip())


def looks_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_FERNET_PREFIX)  # type: ignore[union-attr]


def seal(plaintext: str | None) -> str | None:
    """Encrypt a token for storage. None → None. Already-encrypted → unchanged."""
    if plaintext is None:
        return None
    if looks_encrypted(plaintext):
        return plaintext  # idempotent
    if not _key_present():
        # Dev only. Production boot is blocked without the key.
        log.warning("social.token.unencrypted", reason="INTEGRATION_TOKEN_KEY unset")
        return plaintext
    return crypto.encrypt(plaintext).decode("ascii")


def unseal(stored: str | None) -> str | None:
    """Decrypt a stored token. Legacy plaintext passes through unchanged."""
    if not stored:
        return stored
    if not looks_encrypted(stored):
        return stored  # legacy plaintext written before encryption rollout
    try:
        return crypto.decrypt(stored.encode("ascii"))
    except crypto.InvalidIntegrationToken:
        # Key rotated / corrupt — caller should prompt a reconnect. Don't
        # crash the read path; surface as "no usable token".
        log.error("social.token.undecryptable")
        return None
