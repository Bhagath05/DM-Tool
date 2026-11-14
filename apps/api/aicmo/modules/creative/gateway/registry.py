"""Capability registry. A model is selectable only when it is verified,
configured, and has a server-side executor. Nothing here invents a price.
"""

from __future__ import annotations

from dataclasses import dataclass

from aicmo.config import get_settings


def _openai_configured() -> bool:
    key = get_settings().openai_api_key or ""
    return bool(key) and "replace_me" not in key and not key.endswith("replace_me")


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    provider: str
    task: str
    display_name: str
    output_kind: str
    aspect_ratios: tuple[str, ...]
    resolutions: tuple[str, ...]
    max_duration_s: int | None
    supports_reference_image: bool
    cost_cents: int | None
    cost_unit: str | None
    verified: bool
    unavailable_reason: str | None = None

    def configured(self) -> bool:
        if self.provider == "openai" and self.task == "image.generate":
            return _openai_configured()
        return False

    def available(self) -> bool:
        return self.verified and self.configured() and self.unavailable_reason is None


# Published OpenAI Images list price already used by the existing adapter
# for standard quality. None is used when a provider does not publish a price.
_OPENAI_STANDARD_CENTS = 4


def catalog() -> list[ModelCapability]:
    settings = get_settings()
    veo_reason = "Veo is not a verified adapter in CS-1."
    if not settings.vertex_project:
        veo_reason = "Veo is not configured."
    slideshow_reason = "Slideshow rendering is not a verified generative-video model."
    return [
        ModelCapability(
            model_id="gpt-image-1",
            provider="openai",
            task="image.generate",
            display_name="OpenAI Images",
            output_kind="generative_image",
            aspect_ratios=("1:1", "4:5", "9:16", "16:9"),
            resolutions=("standard",),
            max_duration_s=None,
            supports_reference_image=False,
            cost_cents=_OPENAI_STANDARD_CENTS,
            cost_unit="image",
            verified=True,
            unavailable_reason=None if _openai_configured() else "OpenAI API key is not configured.",
        ),
        ModelCapability(
            model_id="slideshow",
            provider="local",
            task="video.generate",
            display_name="Slideshow",
            output_kind="slideshow",
            aspect_ratios=("9:16", "1:1", "16:9"),
            resolutions=("720p",),
            max_duration_s=60,
            supports_reference_image=True,
            cost_cents=0,
            cost_unit="render",
            verified=False,
            unavailable_reason=slideshow_reason,
        ),
        ModelCapability(
            model_id="veo-3.0-generate-001",
            provider="google",
            task="video.generate",
            display_name="Google Veo",
            output_kind="generative_video",
            aspect_ratios=("16:9", "9:16"),
            resolutions=("720p",),
            max_duration_s=8,
            supports_reference_image=True,
            cost_cents=None,
            cost_unit=None,
            verified=False,
            unavailable_reason=veo_reason,
        ),
    ]


def get_model(model_id: str) -> ModelCapability | None:
    for model in catalog():
        if model.model_id == model_id:
            return model
    return None


def available_for(task: str) -> list[ModelCapability]:
    return [model for model in catalog() if model.task == task and model.available()]
