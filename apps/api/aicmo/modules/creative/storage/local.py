"""LocalDiskBackend — dev/test storage (Creative Core V0).

Writes under `<media_dir>/creative/<key>`; serves via a signed URL the
creative media route verifies. Mirrors the visuals image-serving pattern.
Files live outside the web root; the signed URL is the only access path.
"""

from __future__ import annotations

import time
from pathlib import Path

from aicmo.config import get_settings
from aicmo.modules.creative.storage.base import (
    MediaPersistenceUnavailable,
    StorageRef,
    sign_key,
)


class LocalDiskBackend:
    name = "local"

    def _root(self) -> Path:
        root = Path(get_settings().media_dir) / "creative"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, key: str) -> Path:
        # Keys are tenant-namespaced (e.g. "<org>/<asset>.mp4"); never allow
        # traversal out of the creative root.
        safe = key.replace("..", "_").lstrip("/")
        p = (self._root() / safe).resolve()
        if self._root().resolve() not in p.parents and p != self._root().resolve():
            raise ValueError("storage key escapes creative root")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put(self, *, key: str, data: bytes, content_type: str) -> StorageRef:
        # Production-safety backstop: never persist to ephemeral local disk in
        # production. Render's filesystem is non-durable and not shared across
        # web/worker, so a write here would be silently lost. Fail loudly so
        # the asset is never quietly orphaned. Lifts when MEDIA_BACKEND=s3/r2.
        if not get_settings().media_persistence_available:
            raise MediaPersistenceUnavailable(
                "Object storage is not configured (MEDIA_BACKEND=local in "
                "production). Refusing to write an asset that would be lost."
            )
        self._path(key).write_bytes(data)
        return StorageRef(backend=self.name, key=key)

    def signed_url(self, ref: StorageRef, *, expires_s: int = 3600) -> str:
        exp = int(time.time()) + expires_s
        sig = sign_key(ref.key, exp)
        # The creative media router resolves backend+key → file. Key is
        # URL-encoded by the caller/client as needed.
        return f"/api/v1/media/creative?key={ref.key}&exp={exp}&sig={sig}"

    def read(self, ref: StorageRef) -> bytes:
        return self._path(ref.key).read_bytes()

    def local_path(self, ref: StorageRef) -> Path:
        return self._path(ref.key)

    def delete(self, ref: StorageRef) -> None:
        p = self._path(ref.key)
        if p.exists():
            p.unlink()
