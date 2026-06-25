"""OpenAITTSProvider — real spoken voiceover via OpenAI's /audio/speech.

Gives slideshow reels a genuine narration track using the same OpenAI key
already configured for image generation. No new vendor: pluggable behind the
TTSProvider seam exactly like the stub. Falls back cleanly (caller drops
non-audio bytes → silent reel) if the call fails, so a render never breaks.
"""

from __future__ import annotations

import httpx
import structlog

from aicmo.config import get_settings
from aicmo.modules.video.tts.base import TTSProvider

log = structlog.get_logger()

# OpenAI TTS voices; map our internal voice_id hints to a sensible default.
_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
_DEFAULT_VOICE = "alloy"
# tts-1 pricing ≈ US$15 / 1M chars → 0.0015 cents per char.
_CENTS_PER_1K_CHARS = 2


class OpenAITTSProvider(TTSProvider):
    name = "openai"

    def synthesize(self, text: str, *, voice_id: str, fmt: str = "mp3") -> bytes:
        key = get_settings().openai_api_key
        if not key or key.startswith("sk-ant-"):
            log.warning("tts.openai.no_key")
            return b""
        voice = voice_id if voice_id in _VOICES else _DEFAULT_VOICE
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "tts-1",
                    "input": text[:4000],
                    "voice": voice,
                    "response_format": "mp3",
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:  # noqa: BLE001 — never break a render on a TTS failure
            log.warning("tts.openai.failed", error=str(e))
            return b""

    def estimate_cost(self, *, char_count: int) -> int:
        return int(round(char_count / 1000 * _CENTS_PER_1K_CHARS))
