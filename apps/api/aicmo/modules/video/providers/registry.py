"""Video provider selection — by `video_default_provider`.

`stub` (default) renders offline with no spend; `veo3` is the real Veo 3
adapter (Vertex AI, V1). The Veo provider is constructed eagerly but its
credentials are only checked at submit/poll time, so selecting `veo3`
without Vertex configured fails cleanly at render — never at import."""

from __future__ import annotations

from functools import lru_cache

from aicmo.config import get_settings
from aicmo.modules.video.providers.base import VideoProvider
from aicmo.modules.video.providers.stub import StubVideoProvider
from aicmo.modules.video.providers.veo import VeoProvider


@lru_cache(maxsize=2)
def _stub() -> StubVideoProvider:
    return StubVideoProvider()


@lru_cache(maxsize=2)
def _veo() -> VeoProvider:
    return VeoProvider()


def get_video_provider() -> VideoProvider:
    name = get_settings().video_default_provider
    return _veo() if name == "veo3" else _stub()
