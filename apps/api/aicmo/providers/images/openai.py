"""OpenAI Images provider.

Uses `gpt-image-1` (current generation) which returns base64-encoded
PNG directly — no extra HTTP fetch needed to grab the bytes, unlike
DALL·E 3's URL response.

Cost model (as of 2026-05): roughly $0.04 per 1024×1024 standard image.
We pin the cost to a constant per quality+size rather than parsing the
response (the SDK doesn't surface billing inline). Adjust the constants
if pricing shifts.
"""

from __future__ import annotations

import base64
import time

import structlog
from openai import AsyncOpenAI

from aicmo.config import get_settings
from aicmo.providers.images.base import (
    AspectRatio,
    ImageProvider,
    ImageRenderRequest,
    ImageRenderResult,
)

log = structlog.get_logger()


# gpt-image-1 quality knob: low | medium | high | auto. We expose our own
# internal `standard | hd` so callers don't depend on provider terminology;
# the mapping below survives a provider swap. Costs are gpt-image-1 1024×1024
# list pricing as of 2026 — recheck quarterly.
_QUALITY_FOR_PROVIDER: dict[str, str] = {
    "standard": "medium",  # ~$0.04
    "hd": "high",  # ~$0.17
}

_COST_CENTS_BY_QUALITY: dict[str, int] = {
    "standard": 4,
    "hd": 17,
}

# OpenAI Images currently accepts these explicit sizes only. We map our
# AspectRatio enum to the closest supported size.
_SIZE_FOR_ASPECT: dict[AspectRatio, str] = {
    "1:1": "1024x1024",
    "4:5": "1024x1536",   # OpenAI's portrait
    "9:16": "1024x1536",  # OpenAI doesn't ship true 9:16 — closest portrait
    "16:9": "1536x1024",  # OpenAI's landscape
    "1.91:1": "1536x1024",
}


def _dims(size: str) -> tuple[int, int]:
    w, h = size.split("x")
    return int(w), int(h)


class OpenAIImageProvider(ImageProvider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key or settings.openai_api_key.endswith(
            "replace_me"
        ):
            raise RuntimeError(
                "OPENAI_API_KEY is not set — image rendering is unavailable."
            )
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def render(self, request: ImageRenderRequest) -> ImageRenderResult:
        size = _SIZE_FOR_ASPECT.get(request.aspect_ratio, "1024x1024")
        internal_quality = "hd" if request.quality == "hd" else "standard"
        provider_quality = _QUALITY_FOR_PROVIDER[internal_quality]

        prompt = request.prompt
        if request.negative_prompt:
            prompt = (
                f"{prompt}\n\n"
                f"Strictly avoid: {request.negative_prompt}"
            )

        started = time.monotonic()
        # gpt-image-1 always returns base64; no `response_format` kwarg.
        resp = await self._client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            quality=provider_quality,  # type: ignore[arg-type]
            n=1,
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        if not resp.data or not resp.data[0].b64_json:
            raise RuntimeError(
                "OpenAI Images returned no image data — check API quota / content filters."
            )

        image_bytes = base64.b64decode(resp.data[0].b64_json)
        width, height = _dims(size)

        log.info(
            "image_render.completed",
            provider="openai",
            size=size,
            quality=provider_quality,
            latency_ms=latency_ms,
            bytes=len(image_bytes),
        )

        return ImageRenderResult(
            image_bytes=image_bytes,
            mime_type="image/png",
            width=width,
            height=height,
            provider_image_id=None,  # gpt-image-1 doesn't return a stable id
            cost_cents=_COST_CENTS_BY_QUALITY[internal_quality],
            latency_ms=latency_ms,
            provider_name=self.name,
        )
