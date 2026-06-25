"""StorageBackend abstraction — Creative Core V0.

No video/image bytes ever live in Postgres. PG stores a `StorageRef`
(backend + key); bytes live behind a backend (local disk for dev/tests,
S3-compatible object storage for prod). Signed URLs are the only access
path — no public listing.

The abstraction is the no-vendor-lock-in guarantee: `local` and `s3` are
two impls of the same protocol; adding R2/GCS later is one more class.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from aicmo.config import get_settings


@dataclass(frozen=True, slots=True)
class StorageRef:
    """What Postgres stores — never bytes."""

    backend: str  # 'local' | 's3'
    key: str

    def as_dict(self) -> dict[str, str]:
        return {"backend": self.backend, "key": self.key}

    @classmethod
    def from_parts(cls, backend: str | None, key: str | None) -> "StorageRef | None":
        if not backend or not key:
            return None
        return cls(backend=backend, key=key)


@runtime_checkable
class StorageBackend(Protocol):
    """Put bytes, hand back a signed URL, delete. All media-agnostic."""

    name: str

    def put(self, *, key: str, data: bytes, content_type: str) -> StorageRef: ...

    def signed_url(self, ref: StorageRef, *, expires_s: int = 3600) -> str: ...

    def delete(self, ref: StorageRef) -> None: ...


# ---------------------------------------------------------------------
#  Generic HMAC signing for the creative media route (reuses the same
#  secret as image media; media-agnostic — keyed on the storage key, not
#  an image id).
# ---------------------------------------------------------------------
def _signing_key() -> bytes:
    s = get_settings()
    secret = s.media_signing_secret or s.clerk_secret_key or "dev-media-secret"
    return secret.encode()


def sign_key(key: str, exp: int) -> str:
    msg = f"{key}.{exp}".encode()
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()[:32]


def verify_key(key: str, exp: int, sig: str) -> tuple[bool, str]:
    if exp < int(time.time()):
        return False, "expired"
    expected = sign_key(key, exp)
    if not hmac.compare_digest(expected, sig):
        return False, "bad_signature"
    return True, "ok"
