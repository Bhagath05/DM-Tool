"""CS3 — Strategy fallback + composers produce valid editable designs.

These run offline (no LLM): the deterministic fallback always yields a
multi-format plan, and every composed asset validates against the closed
layer schema — so the priority flow works even without an API key.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.creative.design import composers
from aicmo.modules.creative.design.layer_schema import validate_doc
from aicmo.modules.growth.models import GrowthObjective
from aicmo.modules.growth.strategy import _extract_topic, _fallback_plan
from aicmo.modules.growth.strategy_schemas import AssetSpec, Slide


def _objective(statement="I need 50 qualified cybersecurity leads", kind="get_leads"):
    return GrowthObjective(
        id=uuid.uuid4(), objective_kind=kind, statement=statement,
        audience_hypothesis=None, organization_id=uuid.uuid4(), brand_id=uuid.uuid4(),
    )


# ---- topic extraction (heuristic) ----
@pytest.mark.parametrize("statement,expected", [
    ("I need 50 qualified cybersecurity leads", "cybersecurity"),
    ("Get me more bookings for my clinic", "for my clinic"),
    ("drive sales", "your offer"),
])
def test_extract_topic(statement, expected):
    assert _extract_topic(statement) == expected


# ---- deterministic fallback plan ----
def test_fallback_plan_is_multiformat_and_valid():
    plan = _fallback_plan(_objective(), "lead", ["meta", "google"])
    types = [a.creative_type for a in plan.asset_plan]
    assert types == ["poster", "ad", "carousel", "reel"]
    assert plan.hook and plan.cta_angle and plan.value_prop
    # carousel + reel carry slides
    by_type = {a.creative_type: a for a in plan.asset_plan}
    assert len(by_type["carousel"].slides) == 3
    assert len(by_type["reel"].slides) == 3


def test_fallback_plan_varies_cta_by_category():
    lead = _fallback_plan(_objective(kind="get_leads"), "lead", [])
    sale = _fallback_plan(_objective(statement="drive sales", kind="drive_sales"), "sale", [])
    assert lead.cta_angle != sale.cta_angle


# ---- composers → valid editable LayerDocs ----
def _spec(ct, aspect, slides=()):
    return AssetSpec(
        creative_type=ct, aspect=aspect, headline="Headline", subhead="Sub",
        cta="Get started", slides=[Slide(headline=s) for s in slides],
    )


def test_compose_poster_single_page():
    doc = composers.compose(_spec("poster", "4:5"))
    validate_doc(doc)
    assert len(doc["pages"]) == 1
    assert doc["aspect"] == "4:5"
    roles = {l.get("role") for l in doc["pages"][0]["layers"]}
    assert "headline" in roles and "cta" in roles


def test_compose_ad_has_dominant_cta():
    doc = composers.compose(_spec("ad", "4:5"))
    validate_doc(doc)
    cta_bg = next(l for l in doc["pages"][0]["layers"] if l["id"] == "p0_cta_bg")
    assert cta_bg["w"] >= 0.6  # "big" CTA pill for ads


def test_compose_carousel_one_page_per_slide():
    doc = composers.compose(_spec("carousel", "1:1", slides=["A", "B", "C"]))
    validate_doc(doc)
    assert len(doc["pages"]) == 3
    # CTA only on the last page
    last = doc["pages"][2]["layers"]
    assert any(l.get("role") == "cta" for l in last)
    first = doc["pages"][0]["layers"]
    assert not any(l.get("role") == "cta" for l in first)


def test_compose_reel_scenes_have_duration():
    doc = composers.compose(_spec("reel", "9:16", slides=["Hook", "Value", "CTA"]))
    validate_doc(doc)
    assert len(doc["pages"]) == 3
    assert all(p["duration_ms"] for p in doc["pages"])


def test_compose_carousel_without_slides_falls_back_to_single_page():
    doc = composers.compose(_spec("carousel", "1:1"))  # no slides
    validate_doc(doc)
    assert len(doc["pages"]) == 1


def test_media_type_mapping():
    assert composers.media_type_for("poster") == "image"
    assert composers.media_type_for("carousel") == "carousel"
    assert composers.media_type_for("reel") == "video"


def test_layer_ids_unique_within_doc():
    doc = composers.compose(_spec("carousel", "1:1", slides=["A", "B", "C"]))
    ids = [l["id"] for page in doc["pages"] for l in page["layers"]]
    assert len(ids) == len(set(ids))  # editing relies on unique ids
