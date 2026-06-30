"""Storage backend selection — by `media_backend` config. V0 default: local."""

from __future__ import annotations

from functools import lru_cache

from aicmo.config import get_settings
from aicmo.modules.creative.storage.base import StorageBackend
from aicmo.modules.creative.storage.local import LocalDiskBackend
from aicmo.modules.creative.storage.s3 import S3Backend


@lru_cache(maxsize=2)
def _local() -> LocalDiskBackend:
    return LocalDiskBackend()


@lru_cache(maxsize=2)
def _s3() -> S3Backend:
    return S3Backend()


def get_storage_backend() -> StorageBackend:
    # "s3" and "r2" are both S3-compatible (R2 = AWS-S3 API via a custom
    # endpoint). Selection is purely env-driven; no provider is hardcoded.
    backend = get_settings().media_backend
    return _s3() if backend in ("s3", "r2") else _local()
