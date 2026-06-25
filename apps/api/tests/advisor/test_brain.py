"""Business Brain tests."""

from __future__ import annotations

from types import SimpleNamespace

from aicmo.modules.advisor.brain import (
    brain_completeness,
    brain_has_minimum,
    load_business_brain,
)


def test_load_business_brain_maps_fields():
    profile = SimpleNamespace(
        industry="Cafe",
        business_type="Coffee shop",
        target_audience="Urban professionals who want specialty coffee",
        monthly_budget_band="$500-1000",
        primary_goal_text="Increase foot traffic",
        business_location="Austin, TX",
        competitors=["Starbucks", "Local roaster"],
        business_name="Bean Town",
        preferred_platforms=["Instagram"],
        goals=["Grow revenue"],
    )
    brain = load_business_brain(profile)
    assert brain.industry == "Cafe"
    assert brain.business_type == "Coffee shop"
    assert brain.monthly_budget == "$500-1000"
    assert brain.growth_goal == "Increase foot traffic"
    assert brain.location == "Austin, TX"
    assert len(brain.competitors) == 2


def test_brain_has_minimum_requires_industry_and_audience():
    brain = load_business_brain(
        SimpleNamespace(
            industry="Cafe",
            business_type=None,
            target_audience="Urban professionals who want specialty coffee",
            monthly_budget_band=None,
            primary_goal_text=None,
            business_location=None,
            competitors=[],
            business_name="Test",
            preferred_platforms=[],
            goals=[],
        )
    )
    assert brain_has_minimum(brain) is True


def test_brain_completeness_scores_seven_fields():
    brain = load_business_brain(
        SimpleNamespace(
            industry="Cafe",
            business_type="Coffee shop",
            target_audience="Urban professionals who want specialty coffee",
            monthly_budget_band="$500",
            primary_goal_text="Grow",
            business_location="Austin",
            competitors=["X"],
            business_name="Test",
            preferred_platforms=[],
            goals=[],
        )
    )
    score, steps = brain_completeness(brain)
    assert score == 7
    assert steps == []
