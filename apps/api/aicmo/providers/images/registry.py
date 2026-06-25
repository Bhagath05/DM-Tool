"""Get-by-name registry for image providers.

Single function: `get_image_provider(name)` → ImageProvider. Cached so
each provider is instantiated once per process. Mirrors the LLM router
pattern.
"""

from __future__ import annotations

from functools import lru_cache

from aicmo.providers.images.base import ImageProvider


@lru_cache
def get_image_provider(name: str) -> ImageProvider:
    # Lazy imports — providers may pull in heavy SDKs we don't want to
    # load until first use.
    if name == "openai":
        from aicmo.providers.images.openai import OpenAIImageProvider

        return OpenAIImageProvider()
    raise ValueError(f"Unknown image provider: {name}")
