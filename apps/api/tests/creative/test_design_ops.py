"""CS1-3 — the EditOp grammar + pure apply_ops transform.

The same ops are emitted by the AI (Guided Mode) and the future canvas
(Pro Mode). apply_ops is pure (the source doc is never mutated) and the
result re-validates against the closed schema.
"""

from __future__ import annotations

import pytest

from aicmo.modules.creative.design.layer_schema import validate_doc
from aicmo.modules.creative.design.ops import OpError, apply_ops, parse_ops


def _doc():
    return {
        "version": 1,
        "pages": [{
            "background": {"kind": "color", "color": "#101010"},
            "layers": [
                {"type": "text", "id": "h1", "role": "headline", "text": "Old",
                 "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "color": "#ffffff"},
            ],
        }],
    }


def test_parse_ops_discriminates():
    ops = parse_ops([
        {"op": "set_text", "layer_id": "h1", "text": "New"},
        {"op": "move_layer", "layer_id": "h1", "x": 0.2, "y": 0.3},
    ])
    assert ops[0].op == "set_text" and ops[1].op == "move_layer"


def test_parse_ops_rejects_unknown_op():
    with pytest.raises(Exception):
        parse_ops([{"op": "drop_table", "layer_id": "h1"}])


def test_apply_is_pure():
    src = _doc()
    ops = parse_ops([{"op": "set_text", "layer_id": "h1", "text": "New"}])
    out = apply_ops(src, ops)
    assert out["pages"][0]["layers"][0]["text"] == "New"
    assert src["pages"][0]["layers"][0]["text"] == "Old"  # source untouched


def test_set_text_move_resize():
    out = apply_ops(_doc(), parse_ops([
        {"op": "set_text", "layer_id": "h1", "text": "Hello"},
        {"op": "move_layer", "layer_id": "h1", "x": 0.25, "y": 0.35},
        {"op": "resize_layer", "layer_id": "h1", "w": 0.5, "h": 0.1},
    ]))
    ly = out["pages"][0]["layers"][0]
    assert (ly["text"], ly["x"], ly["y"], ly["w"], ly["h"]) == ("Hello", 0.25, 0.35, 0.5, 0.1)


def test_add_and_delete_layer():
    out = apply_ops(_doc(), parse_ops([
        {"op": "add_layer", "page_index": 0, "layer": {
            "type": "text", "id": "cta", "role": "cta", "text": "Buy",
            "x": 0.1, "y": 0.8, "w": 0.4, "h": 0.1, "color": "brand:primary"}},
    ]))
    assert len(out["pages"][0]["layers"]) == 2
    out2 = apply_ops(out, parse_ops([{"op": "delete_layer", "layer_id": "h1"}]))
    assert [l["id"] for l in out2["pages"][0]["layers"]] == ["cta"]


def test_delete_missing_layer_raises():
    with pytest.raises(OpError):
        apply_ops(_doc(), parse_ops([{"op": "delete_layer", "layer_id": "nope"}]))


def test_update_missing_layer_raises():
    with pytest.raises(OpError):
        apply_ops(_doc(), parse_ops([{"op": "update_layer", "layer_id": "x", "props": {"x": 0.0}}]))


def test_reorder_requires_permutation():
    out = apply_ops(_doc(), parse_ops([
        {"op": "add_layer", "page_index": 0, "layer": {
            "type": "shape", "id": "bg", "x": 0, "y": 0, "w": 1, "h": 1}},
    ]))
    reordered = apply_ops(out, parse_ops([
        {"op": "reorder", "page_index": 0, "layer_ids": ["bg", "h1"]},
    ]))
    assert [l["id"] for l in reordered["pages"][0]["layers"]] == ["bg", "h1"]
    with pytest.raises(OpError):
        apply_ops(out, parse_ops([{"op": "reorder", "page_index": 0, "layer_ids": ["h1"]}]))


def test_apply_brand_token_and_set_animation():
    out = apply_ops(_doc(), parse_ops([
        {"op": "apply_brand_token", "layer_id": "h1", "field": "color", "token": "brand:accent"},
        {"op": "set_animation", "layer_id": "h1", "animation": {"kind": "fade", "duration_ms": 300}},
    ]))
    ly = out["pages"][0]["layers"][0]
    assert ly["color"] == "brand:accent"
    assert ly["animation"]["kind"] == "fade"


def test_pages_add_and_delete():
    out = apply_ops(_doc(), parse_ops([{"op": "add_page", "page": {"layers": []}}]))
    assert len(out["pages"]) == 2
    out2 = apply_ops(out, parse_ops([{"op": "delete_page", "page_index": 1}]))
    assert len(out2["pages"]) == 1
    with pytest.raises(OpError):
        apply_ops(out2, parse_ops([{"op": "delete_page", "page_index": 0}]))  # last page


def test_set_background():
    out = apply_ops(_doc(), parse_ops([
        {"op": "set_background", "page_index": 0, "background": {"kind": "color", "color": "brand:surface"}},
    ]))
    assert out["pages"][0]["background"]["color"] == "brand:surface"


def test_result_revalidates_against_closed_schema():
    out = apply_ops(_doc(), parse_ops([
        {"op": "set_text", "layer_id": "h1", "text": "Valid"},
        {"op": "add_layer", "page_index": 0, "layer": {
            "type": "icon", "id": "ic", "icon_name": "arrow-right", "x": 0.1, "y": 0.1,
            "w": 0.1, "h": 0.1, "color": "#fff"}},
    ]))
    assert validate_doc(out)  # the transformed doc is still schema-valid
