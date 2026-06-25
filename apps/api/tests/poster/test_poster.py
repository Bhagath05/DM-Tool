"""Pure-logic tests for the meaning-first LinkedIn poster studio.

Import only the pure files (copy / template / theme / media) — no SQLAlchemy
model graph, no network — so they run fast and pin the logic the render path
depends on. The hero-image generation + HTML→PNG render are verified live.
"""

from __future__ import annotations

import asyncio

from aicmo.modules.poster import copy as copy_mod
from aicmo.modules.poster import media, theme
from aicmo.modules.poster.schemas import LinkedInCopy
from aicmo.modules.poster.template import render_html


def _copy(**over) -> LinkedInCopy:
    base = dict(
        layout="editorial", palette="bold", image_style="photo",
        image_concept="A warm cafe table with fresh pastries and coffee, no text.",
        eyebrow="Now Live", headline_lead="Meet", headline_accent="Brunch",
        subheadline="Fresh every morning.", cta="Order now",
        bullets=["Fast pickup", "Local beans", "Made fresh"],
        post_body="A real caption with enough words to be a believable LinkedIn post body here.",
        hashtags=["cafe", "brunch"],
    )
    base.update(over)
    return LinkedInCopy(**base)


# ---- copy: fallback + clamp ----


def test_fallback_is_valid_and_offline():
    import aicmo.llm as _llm

    orig = getattr(_llm, "get_llm_router", None)
    _llm.get_llm_router = lambda: (_ for _ in ()).throw(RuntimeError("no-llm"))
    try:
        copy, used_llm = asyncio.run(
            copy_mod.compose("Launch weekend brunch + online ordering", brand_name="Brookie Bar")
        )
    finally:
        if orig:
            _llm.get_llm_router = orig
    assert used_llm is False
    assert copy.layout in {"editorial", "split", "banner"}
    assert copy.image_concept and "no text" not in copy.image_concept.lower()[:0]  # present
    assert len(copy.post_body.split()) >= 40
    assert len(copy.bullets) <= 3


def test_clamp_coerces_enums_and_trims():
    bad = _copy(
        layout="diagram", palette="rainbow", image_style="claymation",  # type: ignore[arg-type]
        bullets=["a", " ", "b", "c", "d"], hashtags=["#x", " y ", ""],
    )
    out = copy_mod.clamp(bad)
    assert out.layout == "editorial"
    assert out.palette == "bold"
    assert out.image_style == "photo"
    assert out.bullets == ["a", "b", "c"]  # trimmed to 3, blanks dropped
    assert out.hashtags == ["x", "y"]


# ---- template: each layout renders + escapes ----


def test_each_layout_renders():
    th = theme.build_theme(palette="warm", brand_name="ACME", website="acme.com")
    for layout in ("editorial", "split", "banner"):
        html = render_html(_copy(layout=layout), th, hero_data_uri="data:image/png;base64,AAAA")
        assert f"class='{layout}'" in html
        assert "Meet" in html and "Brunch" in html
        assert "data:image/png;base64,AAAA" in html  # hero embedded


def test_editorial_uses_hero_as_background():
    th = theme.build_theme(palette="bold", brand_name="X")
    html = render_html(_copy(layout="editorial"), th, hero_data_uri="data:image/png;base64,ZZ")
    assert 'class="heroimg"' in html
    assert 'class="scrim"' in html


def test_fallback_gradient_when_no_hero():
    th = theme.build_theme(palette="cool", brand_name="X")
    html = render_html(_copy(layout="editorial"), th, hero_data_uri=None)
    assert "herofallback" in html


def test_render_html_escapes_brand_and_copy():
    th = theme.build_theme(palette="bold", brand_name="<script>evil</script>", website="x.com")
    html = render_html(_copy(headline_lead="<b>hi</b>"), th, hero_data_uri="d")
    assert "<script>evil</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>hi</b>" not in html


# ---- theme: palette + brand ----


def test_theme_palette_and_brand_override():
    t = theme.build_theme(palette="warm", brand_name="brookie bar", website="http://brookiebar.com/")
    assert t.c1 == "#f6b352"  # warm preset
    assert t.brand_name == "brookie bar"
    assert t.website == "brookiebar.com"
    # brand override beats palette
    t2 = theme.build_theme(palette="warm", brand_name="X", color_primary="#112233")
    assert t2.c1 == "#112233"


# ---- media: signed URL ----


def test_media_sign_roundtrip_and_tamper(monkeypatch):
    monkeypatch.setattr(media, "_secret", lambda: b"unit-test-secret")
    url = media.sign_storage_key("org-1/poster/abc.png")
    import urllib.parse as up

    q = up.parse_qs(url.split("?", 1)[1])
    k, exp, sig = q["k"][0], int(q["exp"][0]), q["sig"][0]
    assert media.verify(k, exp, sig) == "org-1/poster/abc.png"
    assert media.verify(k, exp, "deadbeef" * 5) is None
    assert media.verify(k, 1, media._sig(k, 1)) is None
