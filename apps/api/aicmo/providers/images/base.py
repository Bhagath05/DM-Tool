"""ImageProvider abstract base.

A provider takes a self-contained `ImageRenderRequest` (prompt + size +
nothing-else-needed) and returns the raw bytes of the rendered PNG/JPG
plus minimal metadata. Storage, signing, persistence — all caller's
responsibility. The provider just renders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


AspectRatio = Literal["1:1", "4:5", "9:16", "16:9", "1.91:1"]


@dataclass
class ImageRenderRequest:
    """Everything a provider needs to produce one image.

    `prompt` should be the FINAL natural-language prompt — providers don't
    transform it. The caller (render service) is responsible for composing
    a good prompt from the brief.
    """

    prompt: str
    aspect_ratio: AspectRatio = "1:1"
    # Higher = better quality + more cost. Providers map this to their
    # own quality knob (e.g. OpenAI's `quality` field).
    quality: Literal["standard", "hd"] = "standard"
    # Optional negative prompt / things-to-avoid. Some providers ignore.
    negative_prompt: str | None = None


@dataclass
class ImageRenderResult:
    """What a provider returns to the render service.

    The bytes ARE the image file — caller writes them to disk and serves
    them via a signed URL. We never trust the provider's temporary URL
    long-term (OpenAI's expire in ~60min).
    """

    image_bytes: bytes
    mime_type: str  # e.g. "image/png"
    width: int
    height: int
    # Provider-side identifier of the generation, if any. Lets us audit/refund.
    provider_image_id: str | None
    # USD cents the provider call cost. Best-effort estimate when the API
    # doesn't return billing info — fine for daily-cap tracking.
    cost_cents: int
    # Round-trip latency in milliseconds. Useful for ops.
    latency_ms: int
    # Provider name for the storage row.
    provider_name: str


class ImageProvider(ABC):
    """Implementations live in `aicmo/providers/images/<vendor>.py`."""

    #: Stable identifier used by the registry + persisted on RenderedVisual.
    name: str

    @abstractmethod
    async def render(self, request: ImageRenderRequest) -> ImageRenderResult: ...
