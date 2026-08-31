"""StubVideoProvider — deterministic, no network (V0 + tests).

Proves the whole async pipeline (submit → poll → bytes → storage) end to
end without calling Veo or spending money. `poll` returns `done`
immediately with deterministic bytes + a stub cost from `estimate_cost`,
so the pipeline reaches `ready` in tests.

The bytes are a **structurally valid MP4** (a real `ftyp` box + a `free`
box carrying the op id) so they pass the same provider-output validation
(`validate_video_output`) that guards real Veo bytes before persisting.
A stub whose job is to prove the pipeline must clear that gate honestly —
never by exempting itself from validation.
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


def _minimal_mp4(op_id: str) -> bytes:
    """A tiny but well-formed MP4: an `ftyp` box (so the 'ftyp' magic sits at
    offset 4) followed by a `free` box holding the op id for determinism."""
    ftyp_body = b"isom" + (0).to_bytes(4, "big") + b"isom" + b"mp42"
    ftyp = (8 + len(ftyp_body)).to_bytes(4, "big") + b"ftyp" + ftyp_body
    trailer = f"STUBVIDEO::{op_id}".encode()
    free = (8 + len(trailer)).to_bytes(4, "big") + b"free" + trailer
    return ftyp + free


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
        # Deterministic "render" — never a real network call. Valid MP4 bytes
        # so the pipeline's provider-output validation passes honestly.
        payload = _minimal_mp4(operation.op_id)
        return ProviderStatus(
            state="done",
            result_bytes=payload,
            cost_cents=0,  # cost is attributed via estimate_cost at submit time
            has_native_audio=False,   # we always layer TTS (Decision 1)
            synthid_watermark=False,  # real Veo sets this true in V1
        )

    def estimate_cost(self, *, duration_s: float, width: int, height: int) -> int:
        return int(round(duration_s)) * _STUB_CENTS_PER_SECOND
