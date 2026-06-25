"""No-Veo slideshow reel renderer (Pillow + bundled ffmpeg).

Turns an editable reel `creative_design` into a REAL, playable MP4 with no
external video API: each scene page is rendered to a 1080×1920 frame (hero
image cover + scrim + wrapped copy), then the frames are assembled with the
ffmpeg binary bundled by imageio-ffmpeg, muxing the TTS voiceover. Motion is
slideshow/cut, not generative — but it plays everywhere and needs zero GCP.

The design stays the source of truth; this is one renderer of it. A real Veo
clip path remains available via VIDEO_DEFAULT_PROVIDER=veo3.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from io import BytesIO

import structlog

log = structlog.get_logger()

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

_BRAND_COLORS = {
    "brand:primary": (37, 99, 235), "brand:secondary": (124, 58, 237),
    "brand:accent": (245, 158, 11), "brand:ink": (15, 23, 42),
    "brand:surface": (255, 255, 255), "brand:body": (51, 65, 85),
    "brand:heading": (15, 23, 42),
}


def first_image_asset_id(page: dict) -> str | None:
    """The page's hero image: first image layer that points at a brand asset."""
    for ly in page.get("layers", []):
        if ly.get("type") == "image" and ly.get("asset_id"):
            return str(ly["asset_id"])
    return None


def ffmpeg_available() -> bool:
    try:
        import imageio_ffmpeg  # noqa: PLC0415

        return bool(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001
        return False


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont  # noqa: PLC0415

    for path in (_BOLD_CANDIDATES if bold else []) + _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _color(value: str | None, default=(255, 255, 255)):
    if not value:
        return default
    if value.startswith("brand:"):
        return _BRAND_COLORS.get(value, (148, 163, 184))
    v = value.lstrip("#")
    if len(v) == 6:
        try:
            return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
        except ValueError:
            return default
    return default


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_page_png(page: dict, *, width: int, height: int, image_bytes: bytes | None) -> bytes:
    """Render one design page to a PNG frame."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    bg = page.get("background", {})
    base = _color(bg.get("color"), (15, 18, 32)) if bg.get("kind") == "color" else (15, 18, 32)
    img = Image.new("RGB", (width, height), base)

    # Hero image — cover-fit.
    if image_bytes:
        try:
            photo = Image.open(BytesIO(image_bytes)).convert("RGB")
            pw, ph = photo.size
            scale = max(width / pw, height / ph)
            photo = photo.resize((int(pw * scale), int(ph * scale)))
            x = (photo.width - width) // 2
            y = (photo.height - height) // 2
            img.paste(photo.crop((x, y, x + width, y + height)), (0, 0))
        except Exception as e:  # noqa: BLE001
            log.warning("slideshow.image_decode_failed", error=str(e))

    draw = ImageDraw.Draw(img, "RGBA")
    # Scrim for legibility (slightly stronger at the bottom where the CTA sits).
    draw.rectangle([0, 0, width, height], fill=(11, 18, 32, 110))

    layers = page.get("layers", [])
    # CTA pill (a brand-filled rounded shape) if present.
    for ly in layers:
        if ly.get("type") == "shape" and ly.get("role") == "cta":
            x0, y0 = int(ly.get("x", 0.08) * width), int(ly.get("y", 0.8) * height)
            x1, y1 = x0 + int(ly.get("w", 0.5) * width), y0 + int(ly.get("h", 0.1) * height)
            draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=_color(ly.get("fill")))

    # Text layers.
    for ly in layers:
        if ly.get("type") != "text" or not ly.get("text"):
            continue
        role = ly.get("role")
        size = max(20, int((ly.get("font_size") or 0.05) * height))
        bold = role in ("headline", "cta") or ly.get("weight") in ("bold", "semibold")
        font = _font(size, bold=bold)
        fill = _color(ly.get("color"), (255, 255, 255) if role != "cta" else (255, 255, 255))
        max_w = int((ly.get("w") or 0.84) * width)
        x = int((ly.get("x") or 0.08) * width)
        y = int((ly.get("y") or 0.1) * height)
        align = ly.get("align", "left")
        lines = _wrap(draw, ly["text"], font, max_w)
        for line in lines:
            lw = draw.textlength(line, font=font)
            lx = x + (max_w - lw) // 2 if align == "center" else x
            # subtle shadow for contrast
            draw.text((lx + 2, y + 2), line, font=font, fill=(0, 0, 0, 160))
            draw.text((lx, y), line, font=font, fill=fill)
            y += int(size * 1.18)

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def looks_like_audio(b: bytes | None) -> bool:
    """True only for bytes ffmpeg can actually decode — guards against the
    stub TTS sentinel (`STUBAUDIO::…`) so an offline run yields a valid silent
    MP4 instead of a broken mux."""
    if not b or len(b) < 64:
        return False
    head = b[:4]
    return (
        head[:3] == b"ID3"  # MP3 with ID3 tag
        or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)  # MPEG frame sync
        or head == b"RIFF"  # WAV
        or head == b"OggS"  # Ogg
        or b[4:8] == b"ftyp"  # MP4/M4A container
    )


def assemble_mp4(
    frames: list[tuple[bytes, float]], *, audio_bytes: bytes | None, width: int, height: int, fps: int = 24
) -> bytes:
    """Assemble frames (png_bytes, duration_s) + optional audio → MP4 bytes.
    Non-decodable audio (e.g. the stub TTS sentinel) is dropped → silent MP4."""
    import imageio_ffmpeg  # noqa: PLC0415

    if not looks_like_audio(audio_bytes):
        audio_bytes = None
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    total_s = sum(max(0.5, dur) for _, dur in frames)
    with tempfile.TemporaryDirectory() as d:
        listing = []
        for i, (png, dur) in enumerate(frames):
            fp = os.path.join(d, f"f{i}.png")
            with open(fp, "wb") as fh:
                fh.write(png)
            listing.append(f"file '{fp}'\nduration {max(0.5, dur):.3f}")
        # concat demuxer requires the last image repeated to flush its duration.
        if frames:
            listing.append(f"file '{os.path.join(d, f'f{len(frames) - 1}.png')}'")
        list_path = os.path.join(d, "list.txt")
        with open(list_path, "w") as fh:
            fh.write("\n".join(listing))

        out_path = os.path.join(d, "reel.mp4")
        cmd = [exe, "-y", "-f", "concat", "-safe", "0", "-i", list_path]
        audio_path = None
        if audio_bytes:
            audio_path = os.path.join(d, "vo.mp3")
            with open(audio_path, "wb") as fh:
                fh.write(audio_bytes)
            cmd += ["-i", audio_path]
        cmd += [
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        ]
        if audio_path:
            # Cap to the visual length so every scene always shows fully:
            # shorter VO → trailing silence; longer VO → audio truncated.
            cmd += ["-c:a", "aac", "-b:a", "128k", "-t", f"{total_s:.3f}"]
        cmd += [out_path]

        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[-400:]}")
        with open(out_path, "rb") as fh:
            return fh.read()
