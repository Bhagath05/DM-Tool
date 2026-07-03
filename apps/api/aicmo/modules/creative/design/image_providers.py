"""Image provider abstractions (CS5.1) — background removal, stock search,
and AI image generation.

Same no-vendor-lock pattern as the video/TTS/storage providers: an interface
+ a stub, selected via config. The stubs let the whole image-editing flow
(replace / remove-bg / AI replace / asset search) run end-to-end with NO
external dependency; real providers (e.g. remove.bg, Unsplash, OpenAI Images)
drop in later by implementing the same protocol. Every provider OUTPUT becomes
a NEW tenant-owned brand_asset — originals are never mutated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import structlog
from pydantic import BaseModel

from aicmo.config import get_settings

log = structlog.get_logger()

# Default negatives keep AI hero images text-free + clean (they used to be
# hardcoded inside the OpenAI impl; now they're the fallback when a caller
# doesn't supply its own negative prompt).
_DEFAULT_NEGATIVE = "text, words, letters, captions, watermark, logo, ui, low quality, blurry"

# A minimal valid 1x1 transparent PNG — the stub "generated"/"processed" image.
# Real providers return real bytes; this keeps the pipeline runnable offline.
_TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


# ---------------------------------------------------------------------
#  Background removal
# ---------------------------------------------------------------------
class BgRemovalProvider(Protocol):
    name: str

    def remove(self, data: bytes, content_type: str) -> tuple[bytes, str]:
        """Return (processed_png_bytes, mime). Real impl strips the background
        to transparency; the result is stored as a new asset."""
        ...


class StubBgRemovalProvider:
    name = "stub"

    def remove(self, data: bytes, content_type: str) -> tuple[bytes, str]:
        # Offline stub: emit a transparent PNG placeholder. A real provider
        # returns the actual cut-out. The contract (new transparent asset) holds.
        return _TRANSPARENT_PNG, "image/png"


# ---------------------------------------------------------------------
#  Stock search
# ---------------------------------------------------------------------
class StockResult(BaseModel):
    provider: str
    external_id: str
    label: str
    thumb_url: str
    full_url: str


class StockProvider(Protocol):
    name: str

    async def search(self, query: str, *, limit: int = 12) -> list[StockResult]:
        ...


class StubStockProvider:
    name = "stub"

    async def search(self, query: str, *, limit: int = 12) -> list[StockResult]:
        # No external catalog yet — returns empty so the UI shows "no stock
        # results". A real provider (Unsplash/Pexels) implements this method.
        return []


# ---------------------------------------------------------------------
#  AI image generation (text → image)
# ---------------------------------------------------------------------
_ASPECT = {"1:1": "1:1", "4:5": "4:5", "9:16": "9:16", "16:9": "16:9"}


@dataclass(frozen=True)
class ImageGenRequest:
    """The full generation contract (Phase 6.3, spec #2). Providers consume
    what they support and echo the rest back on the result so the whole
    contract is persistable."""

    prompt: str
    negative_prompt: str | None = None
    aspect: str = "1:1"
    style: str | None = None
    width: int | None = None
    height: int | None = None
    seed: int | None = None


@dataclass(frozen=True)
class ImageGenResult:
    """Bytes + the resolved metadata the caller persists on the asset."""

    image_bytes: bytes
    mime: str
    provider: str
    model: str
    seed: int | None
    width: int | None
    height: int | None
    cost_cents: int
    duration_ms: int


class ImageGenProvider(Protocol):
    name: str

    async def generate(self, request: ImageGenRequest) -> ImageGenResult:
        """Text → image + resolved generation metadata. Stored as a new asset."""
        ...


class StubImageGenProvider:
    name = "stub"

    async def generate(self, request: ImageGenRequest) -> ImageGenResult:
        # Offline placeholder (used only when no OpenAI key is configured). The
        # metadata contract is still fully populated so persistence + tests are
        # provider-independent.
        return ImageGenResult(
            image_bytes=_TRANSPARENT_PNG, mime="image/png", provider="stub",
            model="stub", seed=request.seed, width=request.width,
            height=request.height, cost_cents=0, duration_ms=0,
        )


class OpenAIImageGenProvider:
    """Real text→image via the existing OpenAI image provider (Phase 4-A)."""

    name = "openai"

    async def generate(self, request: ImageGenRequest) -> ImageGenResult:
        from aicmo.providers.images.base import ImageRenderRequest
        from aicmo.providers.images.registry import get_image_provider

        provider = get_image_provider(get_settings().image_default_provider)
        t0 = time.perf_counter()
        result = await provider.render(
            ImageRenderRequest(
                prompt=request.prompt if not request.style
                else f"{request.prompt}\nStyle: {request.style}",
                aspect_ratio=_ASPECT.get(request.aspect, "1:1"),  # type: ignore[arg-type]
                quality="standard",
                negative_prompt=request.negative_prompt or _DEFAULT_NEGATIVE,
            )
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return ImageGenResult(
            image_bytes=result.image_bytes, mime=result.mime_type,
            provider=result.provider_name,
            model=getattr(result, "model", None) or "gpt-image-1",
            seed=request.seed, width=result.width, height=result.height,
            cost_cents=result.cost_cents,
            duration_ms=result.latency_ms or elapsed_ms,
        )


# ---------------------------------------------------------------------
#  Selection (config-driven later; stubs today — no external spend)
# ---------------------------------------------------------------------
def get_bg_removal_provider() -> BgRemovalProvider:
    return StubBgRemovalProvider()


def get_stock_provider() -> StockProvider:
    return StubStockProvider()


def get_image_gen_provider() -> ImageGenProvider:
    # Real OpenAI image generation when a key is configured; offline stub
    # otherwise (so dev/tests never need a key).
    if get_settings().openai_api_key:
        return OpenAIImageGenProvider()
    return StubImageGenProvider()
