"""Media validation for provider-generated output (Phase 7B).

User *uploads* are already validated at the route (allow-list + size bound; see
`creative/design/router.py::validate_brand_asset_type`). This module covers the
other trust boundary: bytes returned by an external **video/media provider**,
which must never be persisted blindly. We check declared content-type against an
allow-list, bound the size, and sniff a magic-byte signature so a provider that
returns an error page / wrong payload can't land as if it were a valid video.
"""

from __future__ import annotations

# Allowed generated-media content-types (the pipeline produces exactly these).
VIDEO_TYPES = frozenset({"video/mp4"})
AUDIO_TYPES = frozenset({"audio/mpeg", "audio/mp4"})
TEXT_TYPES = frozenset({"text/vtt"})

# Size ceilings — a runaway provider response must not exhaust storage/memory.
MAX_VIDEO_BYTES = 512 * 1024 * 1024  # 512 MB
MAX_AUDIO_BYTES = 64 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024


class MediaValidationError(ValueError):
    """Provider-returned media failed validation (type/size/integrity)."""


def _normalize(content_type: str | None) -> str:
    return (content_type or "").lower().split(";")[0].strip()


def _has_mp4_signature(data: bytes) -> bool:
    # ISO-BMFF/MP4: a top-level box whose type (bytes 4..8) is 'ftyp'. The
    # first 4 bytes are the box size, so 'ftyp' sits at offset 4.
    return len(data) >= 12 and data[4:8] == b"ftyp"


def validate_video_output(*, content_type: str | None, data: bytes) -> str:
    """Validate a provider's video bytes before persisting. Returns the
    normalized content-type or raises MediaValidationError.

    Sniffs the MP4 signature so a wrong/error payload can't masquerade as video.
    """
    ct = _normalize(content_type)
    if ct not in VIDEO_TYPES:
        raise MediaValidationError(f"unsupported video content-type: {content_type!r}")
    if not data:
        raise MediaValidationError("empty video payload")
    if len(data) > MAX_VIDEO_BYTES:
        raise MediaValidationError(
            f"video exceeds max size ({len(data)} > {MAX_VIDEO_BYTES} bytes)"
        )
    if not _has_mp4_signature(data):
        raise MediaValidationError("payload is not a valid MP4 (missing 'ftyp' box)")
    return ct


def validate_media_output(*, content_type: str | None, data: bytes) -> str:
    """Generic guard for any generated media (video/audio/captions) before
    persisting. Returns normalized content-type or raises MediaValidationError."""
    ct = _normalize(content_type)
    if ct in VIDEO_TYPES:
        return validate_video_output(content_type=content_type, data=data)
    if ct in AUDIO_TYPES:
        cap = MAX_AUDIO_BYTES
    elif ct in TEXT_TYPES:
        cap = MAX_TEXT_BYTES
    else:
        raise MediaValidationError(f"unsupported media content-type: {content_type!r}")
    if not data:
        raise MediaValidationError("empty media payload")
    if len(data) > cap:
        raise MediaValidationError(f"media exceeds max size ({len(data)} > {cap} bytes)")
    return ct
