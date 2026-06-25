"""Composers — AssetSpec → real editable LayerDoc (CS3, AI Mode real).

Deterministic, on-brand composition from layout primitives + brand tokens +
the strategy's copy. NO industry templates (Law 2): the recipe is chosen by
`creative_type` (poster/ad/carousel/reel), parameterized by the copy. The
output is a normal editable design — every layer can be moved/retyped/restyled
in the Studio afterwards.

CS3 owns layout + copy placement (deterministic). CS4/CS5 add LLM-driven
restructuring + the canvas; the imagery/video render lands in CS6. Brand
colors are emitted as `brand:*` tokens, resolved at render time.
"""

from __future__ import annotations

from typing import Any

from aicmo.modules.creative.design.layer_schema import LayerDoc
from aicmo.modules.growth.strategy_schemas import AssetSpec

# ---- layer factories (normalized 0..1 geometry) ----


def _text(
    lid: str, role: str, text: str, *, x: float, y: float, w: float, h: float,
    color: str = "brand:ink", weight: str = "regular", align: str = "left",
    font_size: float = 0.05, z: int = 2,
) -> dict[str, Any]:
    return {
        "type": "text", "id": lid, "role": role, "text": text,
        "x": x, "y": y, "w": w, "h": h, "color": color, "weight": weight,
        "align": align, "font_size": font_size, "z": z,
    }


def _cta_button(prefix: str, label: str, *, y: float = 0.82, big: bool = False) -> list[dict[str, Any]]:
    """A CTA = a brand-filled pill (shape) + the label on top — both editable."""
    h = 0.12 if big else 0.09
    w = 0.62 if big else 0.5
    return [
        {"type": "shape", "id": f"{prefix}_cta_bg", "role": "cta", "shape": "rect",
         "fill": "brand:primary", "radius": 0.5, "x": 0.08, "y": y, "w": w, "h": h, "z": 1},
        _text(f"{prefix}_cta", "cta", label, x=0.08, y=y + h * 0.28, w=w, h=h * 0.5,
              color="brand:surface", weight="semibold", align="center",
              font_size=0.04 if big else 0.035, z=2),
    ]


def _bg(color: str = "brand:surface") -> dict[str, Any]:
    return {"kind": "color", "color": color}


# ---- recipes ----


def _compose_single(spec: AssetSpec, *, strong: bool) -> list[dict[str, Any]]:
    """Poster / ad — one page. `strong` makes the offer + CTA dominant (ads)."""
    layers: list[dict[str, Any]] = [
        _text("p0_headline", "headline", spec.headline, x=0.08, y=0.10, w=0.84, h=0.26,
              color="brand:ink", weight="bold", align="left",
              font_size=0.11 if strong else 0.095),
    ]
    if spec.subhead:
        layers.append(
            _text("p0_subhead", "subhead", spec.subhead, x=0.08, y=0.40, w=0.84, h=0.20,
                  color="brand:ink", align="left", font_size=0.05)
        )
    layers.extend(_cta_button("p0", spec.cta, y=0.80, big=strong))
    return layers


def _compose_carousel(spec: AssetSpec) -> list[dict[str, Any]]:
    """N slide-pages (problem → solution → proof), CTA on the last page.
    Returns [] when the spec has no slides (caller falls back to a poster)."""
    items = spec.slides
    if not items:
        return []
    last = len(items) - 1
    pages: list[dict[str, Any]] = []
    for i, slide in enumerate(items):
        layers = [
            _text(f"p{i}_headline", "headline", slide.headline, x=0.08, y=0.12, w=0.84, h=0.24,
                  color="brand:ink", weight="bold", align="left", font_size=0.09),
        ]
        if slide.body:
            layers.append(
                _text(f"p{i}_body", "body", slide.body, x=0.08, y=0.40, w=0.84, h=0.30,
                      color="brand:ink", align="left", font_size=0.05)
            )
        if i == last:
            layers.extend(_cta_button(f"p{i}", spec.cta, y=0.80))
        pages.append({"background": _bg(), "layers": layers})
    return pages


def _compose_scenes(spec: AssetSpec) -> list[dict[str, Any]]:
    """Reel / video — N scene-pages with durations; CTA on the final scene."""
    items = spec.slides if spec.slides else []
    pages: list[dict[str, Any]] = []
    last = len(items) - 1
    for i, slide in enumerate(items):
        layers = [
            _text(f"p{i}_headline", "headline", slide.headline, x=0.08, y=0.30, w=0.84, h=0.24,
                  color="brand:ink", weight="bold", align="center", font_size=0.10),
        ]
        if slide.body:
            layers.append(
                _text(f"p{i}_subtitle", "subtitle", slide.body, x=0.08, y=0.58, w=0.84, h=0.16,
                      color="brand:ink", align="center", font_size=0.045)
            )
        if i == last:
            layers.extend(_cta_button(f"p{i}", spec.cta, y=0.78, big=True))
        pages.append({"background": _bg(), "layers": layers, "duration_ms": 2500})
    return pages


_MEDIA_TYPE: dict[str, str] = {
    "poster": "image", "ad": "image", "carousel": "carousel",
    "reel": "video", "video": "video",
}


def media_type_for(creative_type: str) -> str:
    return _MEDIA_TYPE.get(creative_type, "image")


def _apply_background(pages: list[dict[str, Any]], asset_id: str) -> None:
    """Put a full-bleed photo behind each page + a scrim, and switch the copy to
    light so it stays legible on the image. Editable like any other layer."""
    for page in pages:
        bg_layers = [
            {"type": "image", "id": "bg_img", "role": "background", "asset_id": asset_id,
             "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "z": 0, "fit": "cover"},
            {"type": "shape", "id": "bg_scrim", "role": "decoration", "shape": "rect",
             "fill": "#0b1220", "opacity": 0.42, "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "z": 1},
        ]
        for ly in page.get("layers", []):
            if ly.get("type") == "text" and ly.get("role") in ("headline", "subhead", "subtitle", "body"):
                ly["color"] = "#ffffff"
        page["layers"] = bg_layers + page.get("layers", [])


def compose(spec: AssetSpec, *, background_asset_id: str | None = None) -> dict[str, Any]:
    """Compose an AssetSpec into a validated LayerDoc dict. When a generated
    background image is supplied, the creative becomes a real photo-backed ad."""
    if spec.creative_type in ("poster", "ad"):
        pages = [{"background": _bg(), "layers": _compose_single(spec, strong=spec.creative_type == "ad")}]
    elif spec.creative_type == "carousel":
        pages = _compose_carousel(spec)
        if not pages:  # no slides → fall back to a single poster-style page
            pages = [{"background": _bg(), "layers": _compose_single(spec, strong=False)}]
    else:  # reel / video
        pages = _compose_scenes(spec)
        if not pages:
            pages = [{"background": _bg(), "layers": _compose_single(spec, strong=False)}]

    if background_asset_id:
        _apply_background(pages, background_asset_id)

    doc = LayerDoc(aspect=spec.aspect, pages=pages)  # validates the whole doc
    return doc.model_dump(mode="json")
