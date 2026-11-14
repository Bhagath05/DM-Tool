"""Server-side generation. Credentials stay in the existing image adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aicmo.modules.creative.design.image_providers import ImageGenRequest, OpenAIImageGenProvider
from aicmo.modules.creative.gateway.registry import ModelCapability

_TIMEOUT_S = 45.0
_MAX_ATTEMPTS = 2


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationOutput:
    image_bytes: bytes
    mime: str
    width: int | None
    height: int | None
    cost_cents: int | None
    duration_ms: int
    model: str
    provider: str


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ")
    for secret in ("sk-", "api_key", "Bearer "):
        if secret.lower() in text.lower():
            return "The image provider rejected the request."
    return text[:240] or "The image provider failed."


async def generate_image(
    model: ModelCapability,
    *,
    prompt: str,
    aspect_ratio: str,
    resolution: str | None,
) -> GenerationOutput:
    del resolution
    if model.provider != "openai" or model.model_id != "gpt-image-1":
        raise GenerationError("No server-side executor is registered for that model.")
    provider = OpenAIImageGenProvider()
    request = ImageGenRequest(prompt=prompt, aspect=aspect_ratio)
    last_error = "The image provider failed."
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = await asyncio.wait_for(provider.generate(request), timeout=_TIMEOUT_S)
            return GenerationOutput(
                image_bytes=result.image_bytes,
                mime=result.mime,
                width=result.width,
                height=result.height,
                cost_cents=result.cost_cents,
                duration_ms=result.duration_ms,
                model=result.model or model.model_id,
                provider=result.provider or model.provider,
            )
        except TimeoutError:
            last_error = "The image provider timed out."
        except Exception as exc:
            last_error = _safe_error(exc)
            if attempt >= _MAX_ATTEMPTS:
                break
            lowered = last_error.lower()
            if "timed out" not in lowered and "timeout" not in lowered and "connection" not in lowered:
                break
        if attempt >= _MAX_ATTEMPTS:
            break
    raise GenerationError(last_error)
