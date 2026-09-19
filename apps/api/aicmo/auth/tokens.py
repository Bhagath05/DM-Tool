"""Opaque secret tokens for sessions and email/reset links.

One rule governs this module: the raw token is shown to the client exactly
once (a cookie value or an email link) and is NEVER persisted. We store only a
SHA-256 hash of it, and look records up by that hash.

Why SHA-256 (not Argon2) here: unlike a password, these tokens are already
full-entropy (256 bits from `secrets`), so there is nothing to brute-force —
a fast hash is correct and lets us index the hash column for O(1) lookup. The
hash is deterministic (no per-token salt) precisely so the lookup works; that
is safe only because the input is high-entropy random, which it always is.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# 32 bytes = 256 bits of entropy, URL-safe (~43 chars). Comfortably beyond
# guessing for both session cookies and single-use email/reset tokens.
_TOKEN_BYTES = 32


def generate_token(n_bytes: int = _TOKEN_BYTES) -> str:
    """A fresh cryptographically-secure URL-safe token. Return value is the
    RAW secret — hand it to the client once, store only `hash_token(...)`."""
    return secrets.token_urlsafe(n_bytes)


def hash_token(token: str) -> str:
    """Deterministic SHA-256 hex digest used as the storage/lookup key.

    Safe as an unsalted, fast hash only because `token` is high-entropy random
    (see module docstring). Never call this on a low-entropy secret."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Timing-safe string comparison (for comparing hashes/CSRF tokens)."""
    return hmac.compare_digest(a, b)
