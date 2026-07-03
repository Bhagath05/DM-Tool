"""CS5.1 — image editing: replace_image op, crop/mask/fit schema, providers,
NL image-replace helpers. (Service-level remove-bg / AI replace verified live.)
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from aicmo.modules.creative.design import ai_router, image_providers
from aicmo.modules.creative.design.layer_schema import validate_doc
from aicmo.modules.creative.design.ops import apply_ops, parse_ops


def _img_doc(asset_id: str):
    return {
        "version": 1, "aspect": "4:5",
        "pages": [{"background": {"kind": "color", "color": "#111"}, "layers": [
            {"type": "image", "id": "hero", "role": "product", "asset_id": asset_id,
             "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.5, "fit": "cover"},
        ]}],
    }


# ---- schema: crop / mask / fit ----
def test_image_crop_mask_fit_valid():
    a = str(uuid.uuid4())
    doc = _img_doc(a)
    doc["pages"][0]["layers"][0].update(
        {"fit": "stretch", "crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
         "mask": {"kind": "rounded_rect", "radius": 0.2}})
    validate_doc(doc)


@pytest.mark.parametrize("bad", [
    {"fit": "warp"},                              # invalid fit
    {"crop": {"x": 2.0, "y": 0, "w": 1, "h": 1}}, # crop out of range
    {"mask": {"kind": "triangle"}},               # invalid mask kind
])
def test_invalid_image_props_rejected(bad):
    doc = _img_doc(str(uuid.uuid4()))
    doc["pages"][0]["layers"][0].update(bad)
    with pytest.raises(ValidationError):
        validate_doc(doc)


# ---- replace_image op ----
def test_replace_image_op_swaps_asset_and_clears_crop():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    doc = _img_doc(a)
    doc["pages"][0]["layers"][0]["crop"] = {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}
    out = apply_ops(doc, parse_ops([{"op": "replace_image", "layer_id": "hero", "asset_id": b}]))
    ly = out["pages"][0]["layers"][0]
    assert ly["asset_id"] == b and "crop" not in ly
    validate_doc(out)  # still schema-valid


# ---- providers (stubs run offline) ----
def test_bg_removal_returns_png():
    data, mime = image_providers.get_bg_removal_provider().remove(b"x", "image/png")
    assert mime == "image/png" and data[:8] == bytes.fromhex("89504e470d0a1a0a")  # PNG signature


def test_stock_provider_stub_empty():
    assert asyncio.run(image_providers.get_stock_provider().search("luxury office")) == []


def test_image_gen_returns_bytes_and_metadata():
    # Hermetic: exercise the stub directly (never a real provider / real spend).
    req = image_providers.ImageGenRequest(prompt="a doctor", seed=7, style="photo")
    result = asyncio.run(image_providers.StubImageGenProvider().generate(req))
    assert result.image_bytes and result.mime == "image/png"
    # the full contract is populated even on the offline stub
    assert result.provider == "stub" and result.model == "stub"
    assert result.seed == 7
    assert result.cost_cents == 0 and result.duration_ms == 0


# ---- NL image-replace helpers ----
@pytest.mark.parametrize("instruction,expected", [
    ("replace this person with a female doctor", True),
    ("replace the background with an office", True),
    ("swap the logo", True),
    ("make the CTA stronger", False),
])
def test_is_image_replace(instruction, expected):
    assert ai_router.is_image_replace(instruction) is expected


@pytest.mark.parametrize("instruction,target", [
    ("replace this person with a female doctor", "a female doctor"),
    ("replace background with office", "office"),
])
def test_extract_replace_target(instruction, target):
    assert ai_router.extract_replace_target(instruction) == target


def test_first_image_layer_prefers_role_hint():
    doc = {"version": 1, "pages": [{"background": {"kind": "color", "color": "#111"}, "layers": [
        {"type": "image", "id": "bg", "role": "background", "asset_id": str(uuid.uuid4()), "w": 1, "h": 1},
        {"type": "image", "id": "logo", "role": "logo", "asset_id": str(uuid.uuid4()), "w": 0.2, "h": 0.2},
    ]}]}
    assert ai_router.first_image_layer_id(doc, hint="swap the logo") == "logo"
    assert ai_router.first_image_layer_id(doc, hint="replace the photo") == "bg"  # first image
    assert ai_router.first_image_layer_id({"pages": [{"layers": []}]}) is None
