"""StubTTSProvider — deterministic, no network (V0 + tests)."""

from __future__ import annotations

from aicmo.modules.video.tts.base import TTSProvider

# Placeholder pricing — ElevenLabs numbers arrive in V1.
_STUB_CENTS_PER_1K_CHARS = 30


class StubTTSProvider(TTSProvider):
    name = "stub"

    def synthesize(self, text: str, *, voice_id: str, fmt: str = "mp3") -> bytes:
        return f"STUBAUDIO::{voice_id}::{len(text)}chars".encode()

    def estimate_cost(self, *, char_count: int) -> int:
        return int(round(char_count / 1000 * _STUB_CENTS_PER_1K_CHARS))
