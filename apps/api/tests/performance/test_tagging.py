"""Tests for the creative-tag resolver — Phase 9.1.

The classifier is deliberately permissive (never raises). Pin a
small surface so future refactors of keyword groups don't silently
strip a tag.
"""

from __future__ import annotations

from aicmo.modules.performance.tagging import resolve_creative_tags


def test_resolve_tags_returns_all_keys_even_when_empty() -> None:
    tags = resolve_creative_tags()
    for key in (
        "concept_family",
        "emotion",
        "audience",
        "funnel_stage",
        "business_goal",
        "offer_type",
        "platform",
    ):
        assert key in tags


def test_resolve_tags_detects_family_experience_concept() -> None:
    tags = resolve_creative_tags(
        goal="Get more bookings",
        strategy_text="A family dinner — bring the kids and parents together",
    )
    assert tags["concept_family"] == "family_experience"
    assert tags["emotion"] == "warmth"


def test_resolve_tags_detects_consultation_offer() -> None:
    tags = resolve_creative_tags(
        goal="Lead generation",
        strategy_text="Book a free consultation with our experts.",
    )
    assert tags["offer_type"] == "consultation"


def test_resolve_tags_offer_defaults_to_none() -> None:
    tags = resolve_creative_tags(strategy_text="A simple introduction post.")
    assert tags["offer_type"] == "none"


def test_resolve_tags_normalises_platform_aliases() -> None:
    assert resolve_creative_tags(platform="Instagram")["platform"] == "meta"
    assert resolve_creative_tags(platform="adwords")["platform"] == "google"
    assert resolve_creative_tags(platform="LinkedIn")["platform"] == "linkedin"
    assert resolve_creative_tags(platform="random_value")["platform"] == "other"


def test_resolve_tags_audience_slug_from_free_text() -> None:
    tags = resolve_creative_tags(audience="Working parents aged 25 to 45 in Bangalore")
    slug = tags["audience"]
    assert isinstance(slug, str)
    assert "parents" in slug
    assert " " not in slug  # snake-cased


def test_resolve_tags_explicit_funnel_stage_wins() -> None:
    tags = resolve_creative_tags(funnel_stage="conversion", goal="awareness post")
    assert tags["funnel_stage"] == "conversion"


def test_resolve_tags_funnel_inferred_from_text_when_no_explicit() -> None:
    tags = resolve_creative_tags(goal="Drive purchases next weekend")
    assert tags["funnel_stage"] == "conversion"


def test_resolve_tags_never_raises_on_garbage_input() -> None:
    # Empty / None / weird unicode — should never crash.
    resolve_creative_tags()
    resolve_creative_tags(goal="", audience="", strategy_text="")
    resolve_creative_tags(audience="!!!@@@###", strategy_text="🚀🚀🚀")


def test_resolve_tags_truncates_business_goal_to_96_chars() -> None:
    long_goal = "A" * 120
    tags = resolve_creative_tags(business_goal=long_goal)
    assert tags["business_goal"] is not None
    assert len(tags["business_goal"]) == 96
