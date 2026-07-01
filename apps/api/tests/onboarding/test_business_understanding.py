"""Phase 3.1 — AI business-understanding fields on the business profile.

Pins: the new fields default cleanly (back-compat), validate (growth_stage
allowlist), flow through model_dump (→ ORM columns), and reach the strategist
prompt so the AI reasons over them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicmo.modules.onboarding.prompts import build_analysis_user_prompt
from aicmo.modules.onboarding.schemas import (
    BusinessProfileCreate,
    BusinessProfileUpdate,
)


def _valid_create(**over) -> BusinessProfileCreate:
    base = dict(
        business_name="Brew & Bloom Cafe",
        industry="Specialty coffee shop",
        target_audience=(
            "Local remote workers and students who value quality coffee and a "
            "calm space to work"
        ),
        brand_tone="warm",
        goals=["Get more walk-in customers"],
        preferred_platforms=["instagram"],
    )
    base.update(over)
    return BusinessProfileCreate(**base)


def test_new_fields_default_backward_compatible():
    p = _valid_create()  # legacy payload without the new fields
    assert p.products == []
    assert p.services == []
    assert p.unique_selling_points == []
    assert p.pricing is None
    assert p.growth_stage is None


def test_new_fields_flow_through_model_dump():
    p = _valid_create(
        products=["Cold brew", "Pastries"],
        services=["Catering"],
        unique_selling_points=["Single-origin beans", "Quiet work zone"],
        pricing="Premium — ₹150-400 per item",
        growth_stage="growing",
    )
    data = p.model_dump()
    # These keys must map 1:1 to the new ORM columns (create uses **model_dump).
    assert data["products"] == ["Cold brew", "Pastries"]
    assert data["services"] == ["Catering"]
    assert data["unique_selling_points"] == ["Single-origin beans", "Quiet work zone"]
    assert data["pricing"].startswith("Premium")
    assert data["growth_stage"] == "growing"


@pytest.mark.parametrize("stage", ["idea", "launching", "growing", "established", "scaling"])
def test_growth_stage_allowlist_accepts_valid(stage):
    assert _valid_create(growth_stage=stage).growth_stage == stage


def test_growth_stage_rejects_invalid():
    with pytest.raises(ValidationError):
        _valid_create(growth_stage="world-domination")


def test_update_schema_accepts_new_fields_partially():
    u = BusinessProfileUpdate(products=["X"], growth_stage="scaling")
    assert u.products == ["X"]
    assert u.growth_stage == "scaling"
    # Untouched fields stay unset (partial update semantics preserved).
    assert "services" not in u.model_dump(exclude_unset=True)


def test_prompt_includes_business_understanding():
    p = _valid_create(
        products=["Cold brew"],
        unique_selling_points=["Single-origin beans"],
        pricing="Premium tier",
        growth_stage="growing",
    )
    prompt = build_analysis_user_prompt(p)
    assert "Cold brew" in prompt
    assert "Single-origin beans" in prompt
    assert "Premium tier" in prompt
    assert "growing" in prompt


def test_prompt_absent_fields_instruct_inference_not_fabrication():
    prompt = build_analysis_user_prompt(_valid_create())
    # Empty products → the model is told to infer, never invent specifics.
    assert "infer from industry" in prompt
