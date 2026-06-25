"""TTS provider selection — by `tts_default_provider`. V0: stub only."""

from __future__ import annotations

from functools import lru_cache

from aicmo.config import get_settings
from aicmo.modules.video.tts.base import TTSProvider
from aicmo.modules.video.tts.stub import StubTTSProvider


@lru_cache(maxsize=2)
def _stub() -> StubTTSProvider:
    return StubTTSProvider()


@lru_cache(maxsize=2)
def _openai():
    from aicmo.modules.video.tts.openai import OpenAITTSProvider

    return OpenAITTSProvider()


def get_tts_provider() -> TTSProvider:
    name = get_settings().tts_default_provider
    if name == "elevenlabs":
        raise NotImplementedError(
            "the ElevenLabs provider lands in V1 — set TTS_DEFAULT_PROVIDER=stub for V0"
        )
    if name == "openai":
        # Real spoken voiceover when an OpenAI key is configured; otherwise the
        # stub (the slideshow assembler drops its sentinel → silent reel).
        key = get_settings().openai_api_key
        if key and not key.startswith("sk-ant-"):
            return _openai()
        return _stub()
    return _stub()
