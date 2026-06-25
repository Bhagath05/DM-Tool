"""CS4 — NL Edit Router: op conversion/validation, classifier, fallback,
confidence. (LLM-independent: exercises the deterministic fallback + the
server-side validation that guards every LLM suggestion.)
"""

from __future__ import annotations

import asyncio

import pytest

from aicmo.modules.creative.design import ai_router
from aicmo.modules.creative.design.layer_schema import validate_doc
from aicmo.modules.creative.design.ops import apply_ops, parse_ops


def _doc():
    return {
        "version": 1, "aspect": "4:5",
        "pages": [{
            "background": {"kind": "color", "color": "#111"},
            "layers": [
                {"type": "text", "id": "headline", "role": "headline", "text": "Hi",
                 "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "color": "brand:ink"},
                {"type": "text", "id": "cta", "role": "cta", "text": "Buy",
                 "x": 0.1, "y": 0.8, "w": 0.4, "h": 0.1, "color": "brand:primary"},
            ],
        }],
    }


# ---- rule-based classifier ----
@pytest.mark.parametrize("instruction,expected", [
    ("Make this luxury", "restyle"),
    ("Make the CTA stronger", "edit"),
    ("Use brand colors", "edit"),
    ("Make it suitable for LinkedIn", "transform"),
    ("Convert this poster into a carousel", "transform"),
    ("Turn this carousel into a reel", "transform"),
    ("Create 5 variants", "variant"),
    ("Regenerate the copy", "regenerate"),
])
def test_classify(instruction, expected):
    assert ai_router.classify(instruction) == expected


# ---- LlmOp → canonical conversion ----
def test_to_canonical_covers_op_types():
    cases = [
        (ai_router.LlmOp(op="set_text", layer_id="cta", text="Buy now"),
         {"op": "set_text", "layer_id": "cta", "text": "Buy now"}),
        (ai_router.LlmOp(op="move_layer", layer_id="cta", x=0.2, y=0.7),
         {"op": "move_layer", "layer_id": "cta", "x": 0.2, "y": 0.7}),
        (ai_router.LlmOp(op="apply_brand_token", layer_id="cta", field="color", token="brand:primary"),
         {"op": "apply_brand_token", "layer_id": "cta", "field": "color", "token": "brand:primary"}),
        (ai_router.LlmOp(op="set_background_color", color="#222"),
         {"op": "set_background", "page_index": 0, "background": {"kind": "color", "color": "#222"}}),
    ]
    for llm_op, expected in cases:
        assert ai_router._to_canonical(llm_op) == expected


def test_to_canonical_drops_incomplete_ops():
    assert ai_router._to_canonical(ai_router.LlmOp(op="set_text", layer_id="cta")) is None  # no text
    assert ai_router._to_canonical(ai_router.LlmOp(op="move_layer", layer_id="cta")) is None  # no x/y


def test_update_text_style_builds_props():
    op = ai_router.LlmOp(op="update_text_style", layer_id="cta", weight="bold", font_size=0.05)
    canon = ai_router._to_canonical(op)
    assert canon == {"op": "update_layer", "layer_id": "cta", "props": {"weight": "bold", "font_size": 0.05}}


# ---- validation drops missing-layer / bad ops ----
def test_validate_ops_drops_missing_layer():
    raw = [
        {"op": "set_text", "layer_id": "cta", "text": "ok"},      # exists
        {"op": "set_text", "layer_id": "ghost", "text": "no"},    # missing layer
    ]
    kept, dropped = ai_router._validate_ops(raw, _doc())
    assert len(kept) == 1 and dropped == 1
    assert kept[0]["layer_id"] == "cta"


# ---- fallback planner produces valid, applicable ops ----
def test_fallback_cta_stronger_emboldens_cta():
    plan = asyncio.run(ai_router.plan_edit("Make the CTA stronger", _doc(), allow_llm=False))
    assert plan.op_class == "edit" and plan.source == "fallback"
    assert plan.ops and plan.ops[0]["op"] == "update_layer" and plan.ops[0]["layer_id"] == "cta"
    # the ops actually apply + revalidate
    out = apply_ops(_doc(), parse_ops(plan.ops))
    validate_doc(out)


def test_fallback_use_brand_colors():
    plan = asyncio.run(ai_router.plan_edit("Use brand colors", _doc(), allow_llm=False))
    assert plan.op_class == "edit"
    assert all(o["op"] == "apply_brand_token" for o in plan.ops)


def test_fallback_transform_sets_kind_and_aspect():
    p = asyncio.run(ai_router.plan_edit("Make it suitable for LinkedIn", _doc(), allow_llm=False))
    assert p.op_class == "transform" and p.transform_kind == "reformat" and p.target_aspect == "1:1"
    p2 = asyncio.run(ai_router.plan_edit("Convert this poster into a carousel", _doc(), allow_llm=False))
    assert p2.transform_kind == "recompose"
    p3 = asyncio.run(ai_router.plan_edit("Turn this carousel into a reel", _doc(), allow_llm=False))
    assert p3.transform_kind == "remediate" and p3.target_aspect == "9:16"


def test_fallback_variant_count_parsed():
    p = asyncio.run(ai_router.plan_edit("Create 5 variants", _doc(), allow_llm=False))
    assert p.op_class == "variant" and p.variant_count == 5


def test_fallback_restyle_carries_style():
    p = asyncio.run(ai_router.plan_edit("Make this luxury", _doc(), allow_llm=False))
    assert p.op_class == "restyle" and p.style and "luxury" in p.style.lower()


# ---- confidence: empty edit ops → low ----
def test_empty_edit_plan_low_confidence():
    empty_doc = {"version": 1, "pages": [{"background": {"kind": "color", "color": "#111"}, "layers": []}]}
    p = asyncio.run(ai_router.plan_edit("Make the CTA stronger", empty_doc, allow_llm=False))
    # no text/cta layer to target → no ops → low confidence
    assert p.ops == [] and p.confidence <= 25
