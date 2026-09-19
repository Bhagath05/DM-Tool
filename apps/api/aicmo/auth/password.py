"""Password hashing for first-party DM Tool authentication.

Argon2id via `argon2-cffi` (a binding over the reference implementation) — we
never roll our own KDF. The library generates a fresh cryptographically-random
salt per hash and encodes the algorithm, parameters, and salt into the returned
PHC string, so a single self-describing column stores everything `verify` needs
(no separate salt column, no parameter drift bugs).

Parameters follow OWASP's Argon2id guidance (>= 19 MiB memory; we use 64 MiB).
Nothing in this module logs, returns, or otherwise exposes the plaintext.
"""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# One shared hasher. Argon2id (Type.ID) resists both GPU cracking (memory-hard)
# and side-channel attacks. Tuned for an interactive login: ~tens of ms.
_HASHER = PasswordHasher(
    time_cost=3,  # iterations
    memory_cost=64 * 1024,  # 64 MiB in KiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Return a PHC-format Argon2id hash string. Store this verbatim.

    The salt and parameters are embedded, so the caller keeps no other secret.
    """
    return _HASHER.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """True iff `password` matches `stored_hash`. Never raises on a bad password
    or a malformed/foreign hash — a wrong password and an unparseable hash both
    return False so callers can't accidentally leak *why* via an exception."""
    try:
        return _HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True if `stored_hash` was made with weaker parameters than the current
    policy — the caller should re-hash the (already verified) password and
    persist the upgrade. Fails safe to False on a hash we can't parse."""
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except (InvalidHashError, VerificationError):
        return False
