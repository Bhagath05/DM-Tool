"""VeoProvider V1 — Google Veo 3 via Vertex AI (the first real VideoProvider).

Implements the same `VideoProvider` ABC the stub does, so the whole pipeline
(submit → poll → bytes → storage → assembly) is unchanged — only the seam is
real. Veo renders are genuinely long-running, so `submit` kicks off a Vertex
long-running operation and `poll` checks it (the Arq worker rides the op
without blocking).

Supports text-to-video and image-to-video (`seed_image`). The google-genai
SDK is imported LAZILY and credentials are checked at call time, so:
  - the module imports with no SDK/creds installed,
  - selecting `veo3` without a configured Vertex project raises a CLEAR error
    at render time (the job records it as failed_rendering), never a silent
    fallback or a crash at boot.

No vendor lock-in: Runway/Sora/Kling later are just more impls of the ABC.
"""

from __future__ import annotations

from aicmo.config import get_settings
from aicmo.modules.video.providers.base import (
    ProviderOperation,
    ProviderStatus,
    VideoProvider,
)

# Veo 3 (with native audio) list pricing is ~$0.50–0.75 / second. Kept as a
# constant for the pre-flight cost gate; tune to the contracted rate.
_VEO_CENTS_PER_SECOND = 75

_MODEL = "veo-3.0-generate-001"


class VeoConfigError(RuntimeError):
    """Veo selected but Vertex AI isn't configured (project/location/creds)."""


class VeoProvider(VideoProvider):
    name = "veo3"

    def _client(self):
        """Build a Vertex-mode google-genai client. Lazy import + cred guard."""
        settings = get_settings()
        if not settings.vertex_project:
            raise VeoConfigError(
                "Veo 3 needs VERTEX_PROJECT (+ a Veo-enabled Vertex project and "
                "GOOGLE_APPLICATION_CREDENTIALS). Set VIDEO_DEFAULT_PROVIDER=stub to "
                "render without Veo."
            )
        try:
            from google import genai  # noqa: PLC0415 — lazy on purpose
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise VeoConfigError(
                "google-genai is not installed — `pip install google-genai` to use Veo 3."
            ) from e
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location or "us-central1",
        )

    def submit(
        self,
        prompt: str,
        *,
        aspect: str,
        width: int,
        height: int,
        duration_s: float,
        seed_image: bytes | None = None,
        negative_prompt: str | None = None,
    ) -> ProviderOperation:
        client = self._client()
        from google.genai import types  # noqa: PLC0415

        config = types.GenerateVideosConfig(
            aspect_ratio=aspect or "9:16",
            duration_seconds=int(round(duration_s)),
            number_of_videos=1,
            negative_prompt=negative_prompt or None,
        )
        image = (
            types.Image(image_bytes=seed_image, mime_type="image/png")
            if seed_image else None
        )
        operation = client.models.generate_videos(
            model=_MODEL, prompt=prompt, image=image, config=config
        )
        # `operation.name` is the long-running op key we poll on.
        return ProviderOperation(op_id=operation.name, provider=self.name)

    def poll(self, operation: ProviderOperation) -> ProviderStatus:
        client = self._client()
        from google.genai import types  # noqa: PLC0415

        op = client.operations.get(types.GenerateVideosOperation(name=operation.op_id))
        if not getattr(op, "done", False):
            return ProviderStatus(state="pending")
        err = getattr(op, "error", None)
        if err:
            return ProviderStatus(state="failed", error=str(err))
        try:
            video = op.response.generated_videos[0].video
        except (AttributeError, IndexError):
            return ProviderStatus(state="blocked", error="no video in response (safety filter?)")
        data = getattr(video, "video_bytes", None)
        if data is None:
            # Some responses hand back a GCS/remote URI instead of bytes.
            return ProviderStatus(
                state="done", remote_uri=getattr(video, "uri", None),
                has_native_audio=True, synthid_watermark=True,
            )
        return ProviderStatus(
            state="done", result_bytes=data,
            has_native_audio=True,      # Veo 3 generates native audio
            synthid_watermark=True,     # Veo outputs are SynthID-watermarked
        )

    def estimate_cost(self, *, duration_s: float, width: int, height: int) -> int:
        return int(round(duration_s)) * _VEO_CENTS_PER_SECOND
