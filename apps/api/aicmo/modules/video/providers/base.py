"""VideoProvider abstraction — Creative Core V0.

The no-vendor-lock-in seam. Veo 3 is the first impl (V1, via Vertex AI
service account + long-running operation); the stub backs V0/tests.
Runway/Sora/Kling later are just more impls of this ABC.

Every clip is async: `submit` kicks off a provider operation, `poll`
checks it (so the Arq worker rides Veo's long-running op without
blocking), and the result is bytes handed to a StorageBackend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderOperation:
    """Handle to an in-flight render. `op_id` is the poll key (Veo's
    long-running operation name in V1)."""

    op_id: str
    provider: str


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    state: str  # 'pending' | 'done' | 'failed' | 'blocked'
    result_bytes: bytes | None = None
    remote_uri: str | None = None
    error: str | None = None
    cost_cents: int = 0
    has_native_audio: bool = False
    synthid_watermark: bool = False


class VideoProvider(ABC):
    name: str

    @abstractmethod
    def submit(
        self,
        prompt: str,
        *,
        aspect: str,
        width: int,
        height: int,
        duration_s: float,
        seed_image: bytes | None = None,
        negative_prompt: str | None = None,
    ) -> ProviderOperation: ...

    @abstractmethod
    def poll(self, operation: ProviderOperation) -> ProviderStatus: ...

    @abstractmethod
    def estimate_cost(self, *, duration_s: float, width: int, height: int) -> int:
        """Estimated cents for one clip — used for the pre-flight gate."""
        ...
