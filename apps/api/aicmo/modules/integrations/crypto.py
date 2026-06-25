"""Token encryption for the integration framework.

Single-key Fernet (symmetric). The key is read from
`Settings.integration_token_key` exactly once per process, validated
on first use, and held in a module-level cache to avoid re-parsing.

Why not lazy at boot:
  - Dev / test environments often run without any integration
    connected. Requiring the key at startup would force every
    contributor to set a key just to run the unit tests for an
    unrelated module.
  - Production environments that actually use integrations will
    trip `MissingIntegrationKey` on the first connect/sync attempt
    and fail loudly there — same fail-fast intent, scoped to where
    it matters.

Key rotation is OUT OF SCOPE for Phase 10.2a (per the user decision
in the plan). The `rotated_at` column on `integration_credential`
lets a future phase implement a re-encrypt sweep without schema
change.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from aicmo.config import get_settings


class MissingIntegrationKey(RuntimeError):
    """`INTEGRATION_TOKEN_KEY` is unset but a caller tried to
    encrypt/decrypt a token. Surfaces as a 500 with a clear log line
    in production; tests assert that no production code path can
    reach decrypt without the key present."""


class InvalidIntegrationToken(RuntimeError):
    """Ciphertext failed Fernet's MAC check. Either the key changed
    or the row was tampered with. Never expose the raw error to the
    API — log it server-side and tell the founder to reconnect."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Build the Fernet instance lazily — first call validates the key,
    every subsequent call returns the cached instance. lru_cache size=1
    is the canonical singleton-in-a-function pattern."""
    key = get_settings().integration_token_key.strip()
    if not key:
        raise MissingIntegrationKey(
            "INTEGRATION_TOKEN_KEY is unset. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in .env."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise MissingIntegrationKey(
            f"INTEGRATION_TOKEN_KEY is set but not a valid Fernet key: {exc}. "
            "Must be 32 url-safe base64-encoded bytes (44 chars)."
        ) from exc


def encrypt(plaintext: str) -> bytes:
    """Encrypt a plaintext token for storage. Returns bytes that go
    directly into a `BYTEA` column."""
    if plaintext is None:
        raise ValueError("encrypt(): plaintext cannot be None")
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt a stored ciphertext back to a UTF-8 string. Raises
    `InvalidIntegrationToken` if the ciphertext doesn't validate —
    callers should treat that as "tell the founder to reconnect this
    integration" rather than retrying."""
    if not ciphertext:
        raise ValueError("decrypt(): ciphertext is empty")
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise InvalidIntegrationToken(
            "Stored token failed integrity check. The encryption key "
            "may have changed; the integration must be reconnected."
        ) from exc


def reset_for_tests() -> None:
    """Drop the cached Fernet instance so tests can swap the key
    between cases. Production code never calls this."""
    _fernet.cache_clear()
