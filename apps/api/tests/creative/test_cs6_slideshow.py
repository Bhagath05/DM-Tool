"""CS6 — no-Veo slideshow renderer (Pillow frames + bundled ffmpeg).

Pure-ish unit pins for the slideshow seam: page→PNG frame, audio sniffing
(so the stub TTS sentinel never breaks a mux), hero-asset resolution, and a
real frames→MP4 assembly. The DB-backed render job is verified live against
Postgres; these keep the offline pieces honest in CI.
"""

from __future__ import annotations

import subprocess

import pytest

from aicmo.config import get_settings
from aicmo.modules.video import slideshow

PIL = pytest.importorskip("PIL")
imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")


_TEXT_PAGE = {
    "background": {"kind": "color", "color": "#0b1220"},
    "layers": [
        {"type": "text", "role": "headline", "text": "Need 50 qualified leads?",
         "x": 0.08, "y": 0.3, "w": 0.84, "font_size": 0.06, "align": "center", "color": "#ffffff"},
        {"type": "shape", "role": "cta", "x": 0.2, "y": 0.78, "w": 0.6, "h": 0.09, "fill": "brand:primary"},
        {"type": "text", "role": "cta", "text": "Book a demo",
         "x": 0.2, "y": 0.795, "w": 0.6, "font_size": 0.04, "align": "center", "color": "#ffffff"},
    ],
}


def _png_bytes(w=64, h=64, color=(20, 40, 90)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


# ---- frame rendering (Pillow only) ----
def test_render_page_png_is_valid_png_of_size():
    out = slideshow.render_page_png(_TEXT_PAGE, width=1080, height=1920, image_bytes=None)
    assert out[:4].hex() == "89504e47"  # PNG signature
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(out)).size == (1080, 1920)


def test_render_page_png_with_hero_image_covers():
    # A non-9:16 hero must be cover-cropped to the frame without error.
    out = slideshow.render_page_png(
        _TEXT_PAGE, width=1080, height=1920, image_bytes=_png_bytes(800, 600)
    )
    assert out[:4].hex() == "89504e47"


def test_render_page_png_tolerates_garbage_image_bytes():
    out = slideshow.render_page_png(_TEXT_PAGE, width=540, height=960, image_bytes=b"not-an-image")
    assert out[:4].hex() == "89504e47"  # falls back to the base background


# ---- audio sniffing (guards the stub TTS sentinel) ----
def test_looks_like_audio_rejects_stub_sentinel():
    assert slideshow.looks_like_audio(b"STUBAUDIO::stub-voice::42chars") is False


def test_looks_like_audio_rejects_small_or_empty():
    assert slideshow.looks_like_audio(None) is False
    assert slideshow.looks_like_audio(b"") is False
    assert slideshow.looks_like_audio(b"\xff\xf3" + b"\x00" * 10) is False  # too short


def test_looks_like_audio_accepts_id3_and_frame_sync():
    assert slideshow.looks_like_audio(b"ID3" + b"\x00" * 80) is True
    assert slideshow.looks_like_audio(b"\xff\xfb" + b"\x00" * 80) is True


# ---- hero asset resolution ----
def test_first_image_asset_id():
    page = {"layers": [
        {"type": "text", "text": "hi"},
        {"type": "image", "asset_id": "abc-123"},
        {"type": "image", "asset_id": "def-456"},
    ]}
    assert slideshow.first_image_asset_id(page) == "abc-123"


def test_first_image_asset_id_none_when_absent():
    assert slideshow.first_image_asset_id({"layers": [{"type": "text", "text": "x"}]}) is None
    assert slideshow.first_image_asset_id({"layers": [{"type": "image"}]}) is None  # no asset_id


# ---- assembly (frames → real MP4 via bundled ffmpeg) ----
def _probe(mp4: bytes) -> str:
    import os
    import tempfile

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    d = tempfile.mkdtemp()
    p = os.path.join(d, "o.mp4")
    with open(p, "wb") as fh:
        fh.write(mp4)
    return subprocess.run([exe, "-i", p], capture_output=True, text=True).stderr


def test_assemble_mp4_silent_is_h264_with_summed_duration():
    f = slideshow.render_page_png(_TEXT_PAGE, width=540, height=960, image_bytes=None)
    mp4 = slideshow.assemble_mp4([(f, 1.0), (f, 1.0)], audio_bytes=None, width=540, height=960, fps=24)
    assert mp4[4:8] == b"ftyp"  # MP4 container
    info = _probe(mp4)
    assert "Video: h264" in info
    assert "00:00:02.0" in info  # 1.0 + 1.0
    assert "Audio:" not in info  # no audio input → silent


def test_assemble_mp4_drops_non_audio_bytes():
    f = slideshow.render_page_png(_TEXT_PAGE, width=540, height=960, image_bytes=None)
    mp4 = slideshow.assemble_mp4(
        [(f, 1.0)], audio_bytes=b"STUBAUDIO::x::1chars", width=540, height=960, fps=24
    )
    assert "Audio:" not in _probe(mp4)  # sentinel rejected → still a valid silent MP4


# ---- config seam ----
def test_config_accepts_slideshow_provider(monkeypatch):
    monkeypatch.setenv("VIDEO_DEFAULT_PROVIDER", "slideshow")
    get_settings.cache_clear()
    try:
        assert get_settings().video_default_provider == "slideshow"
    finally:
        monkeypatch.delenv("VIDEO_DEFAULT_PROVIDER", raising=False)
        get_settings.cache_clear()
