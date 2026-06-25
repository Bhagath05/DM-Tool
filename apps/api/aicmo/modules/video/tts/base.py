"""TTSProvider abstraction — Creative Core V0.

Decision 1+2: audio is ALWAYS our TTS layer (Veo native audio is muted in
assembly) for brand-voice consistency; ElevenLabs is the first impl (V1),
stub backs V0. Pluggable: Google/OpenAI TTS later are more impls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    name: str

    @abstractmethod
    def synthesize(self, text: str, *, voice_id: str, fmt: str = "mp3") -> bytes: ...

    @abstractmethod
    def estimate_cost(self, *, char_count: int) -> int:
        """Estimated cents for the synthesis."""
        ...
