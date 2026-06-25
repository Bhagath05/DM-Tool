"""CS1-3 — the closed layer schema is the validation spine (Law 3).

These prove that NO mode (AI or human) can write an invalid or unsafe
design: unknown keys, a raw-HTML layer type, bad colors, out-of-bounds
geometry, and cross-tenant asset refs are all rejected.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from aicmo.modules.creative.design.layer_schema import (
    CrossTenantAssetRef,
    LayerDoc,
    assert_tenant_refs,
    collect_asset_refs,
    validate_doc,
)


def _doc(**over):
    base = {
        "version": 1,
        "format_slug": "instagram_reels",
        "pages": [{
            "background": {"kind": "color", "color": "#101010"},
            "layers": [
                {"type": "text", "id": "h1", "role": "headline", "text": "Hi",
                 "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "color": "brand:primary"},
            ],
        }],
    }
    base.update(over)
    return base


def test_minimal_valid_doc():
    doc = validate_doc(_doc())
    assert isinstance(doc, LayerDoc)
    assert doc.pages[0].layers[0].role == "headline"


def test_empty_doc_defaults_to_one_page():
    doc = LayerDoc()
    assert len(doc.pages) == 1


def test_unknown_key_rejected():
    # Simulates injection of an arbitrary/script-bearing key.
    bad = _doc()
    bad["pages"][0]["layers"][0]["onclick"] = "alert(1)"
    with pytest.raises(ValidationError):
        validate_doc(bad)


def test_raw_html_layer_type_rejected():
    # The union is CLOSED — there is no html/raw/script layer type.
    bad = _doc()
    bad["pages"][0]["layers"] = [{"type": "html", "id": "x", "content": "<script>"}]
    with pytest.raises(ValidationError):
        validate_doc(bad)


def test_bad_color_rejected():
    bad = _doc()
    bad["pages"][0]["layers"][0]["color"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        validate_doc(bad)


def test_out_of_bounds_geometry_rejected():
    bad = _doc()
    bad["pages"][0]["layers"][0]["x"] = 5.0  # way outside the canvas
    with pytest.raises(ValidationError):
        validate_doc(bad)


def test_brand_token_color_and_font_accepted():
    ok = _doc()
    ok["pages"][0]["layers"][0]["color"] = "brand:accent"
    ok["pages"][0]["layers"][0]["font_family"] = "brand:heading"
    doc = validate_doc(ok)
    assert doc.pages[0].layers[0].color == "brand:accent"


def test_hex_color_accepted():
    ok = _doc()
    ok["pages"][0]["layers"][0]["color"] = "#ffcc00"
    assert validate_doc(ok)


def test_collect_asset_refs_includes_nested_group_and_background():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doc = validate_doc(_doc(pages=[{
        "background": {"kind": "image", "asset_id": str(a)},
        "layers": [
            {"type": "image", "id": "img1", "asset_id": str(b), "w": 0.5, "h": 0.5},
            {"type": "group", "id": "g1", "children": [
                {"type": "image", "id": "img2", "asset_id": str(c), "w": 0.3, "h": 0.3},
            ]},
        ],
    }]))
    assert collect_asset_refs(doc) == {a, b, c}


def test_assert_tenant_refs_passes_for_owned():
    a = uuid.uuid4()
    doc = validate_doc(_doc(pages=[{
        "layers": [{"type": "image", "id": "i", "asset_id": str(a), "w": 0.5, "h": 0.5}],
    }]))
    assert_tenant_refs(doc, {a})  # no raise


def test_assert_tenant_refs_rejects_foreign():
    owned, foreign = uuid.uuid4(), uuid.uuid4()
    doc = validate_doc(_doc(pages=[{
        "layers": [{"type": "image", "id": "i", "asset_id": str(foreign), "w": 0.5, "h": 0.5}],
    }]))
    with pytest.raises(CrossTenantAssetRef):
        assert_tenant_refs(doc, {owned})
