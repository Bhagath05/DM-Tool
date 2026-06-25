"""StubVideoProvider — deterministic, no network (V0 + tests).

Proves the whole async pipeline (submit → poll → bytes → storage) end to
end without calling Veo or spending money. `poll` returns `done`
immediately with a few deterministic bytes + a stub cost from
`estimate_cost`, so the pipeline reaches `ready` in tests.
"""

from __future__ import annotations

import uuid

from aicmo.modules.video.providers.base import (
    ProviderOperation,
    ProviderStatus,
    VideoProvider,
)

# Placeholder pricing — real numbers arrive with the Veo impl in V1.
_STUB_CENTS_PER_SECOND = 50


class StubVideoProvider(VideoProvider):
    name = "stub"

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
    ) -> ProviderOperation:
        return ProviderOperation(op_id=f"stub-{uuid.uuid4().hex}", provider=self.name)

    def poll(self, operation: ProviderOperation) -> ProviderStatus:
        # Deterministic "render" — never a real network call.
        payload = f"STUBVIDEO::{operation.op_id}".encode()
        return ProviderStatus(
            state="done",
            result_bytes=payload,
            cost_cents=0,  # cost is attributed via estimate_cost at submit time
            has_native_audio=False,   # we always layer TTS (Decision 1)
            synthid_watermark=False,  # real Veo sets this true in V1
        )

    def estimate_cost(self, *, duration_s: float, width: int, height: int) -> int:
        return int(round(duration_s)) * _STUB_CENTS_PER_SECOND
