"""Phase 3.2 — Marketing Strategist unit tests.

Lightweight: the pure logic (prompt grounding, the LLM call, schema contract)
is exercised with a duck-typed profile + a mocked LLM router — no DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from aicmo.modules.strategist import prompts, service
from aicmo.modules.strategist.schemas import MarketingStrategy


def _profile(**over):
    base = dict(
        business_name="Brew & Bloom Cafe",
        industry="Specialty coffee shop",
        business_type="cafe",
        products=["Cold brew", "Pastries"],
        services=["Catering"],
        unique_selling_points=["Single-origin beans"],
        pricing="Premium",
        growth_stage="growing",
        business_location="Hyderabad",
        target_audience="Remote workers and students who value good coffee",
        current_monthly_leads_band="10-50",
        monthly_budget_band="₹10k-25k",
        brand_tone="warm",
        primary_goal_text="Get 50 new customers this month",
        goals=["More walk-ins"],
        preferred_platforms=["instagram"],
        competitors=["Roasted Down the Road"],
        analysis=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _pillar(focus="X"):
    return {"focus": focus, "why": "fits the audience", "actions": ["do a"], "priority": "high"}


def _valid_strategy():
    period = {"period": "This week", "focus": "launch", "milestones": ["m1", "m2", "m3"]}
    return {
        "positioning": "A cozy specialty cafe for remote workers.",
        "target_summary": "Local remote workers who value quality + calm.",
        "content": _pillar("reels"),
        "seo": _pillar("local keywords"),
        "local_seo": _pillar("Google Business Profile"),
        "paid_ads": _pillar("geo-targeted IG ads"),
        "organic_social": _pillar("daily stories"),
        "email": _pillar("loyalty list"),
        "influencer": _pillar("local micro-influencers"),
        "customer_funnel": [
            {"stage": "awareness", "goal": "be discovered", "tactics": ["reels"]},
            {"stage": "conversion", "goal": "first visit", "tactics": ["first-visit offer"]},
        ],
        "campaign_roadmap": ["Grand-opening push", "Weekday work-from-here"],
        "weekly_plan": period,
        "monthly_plan": {**period, "period": "Month 1"},
        "quarterly_plan": {**period, "period": "Q1"},
        "recommendation": "Launch a weekday 'work from here' loyalty card.",
        "reason": "Seating + remote-worker audience is the clearest edge.",
        "confidence": 74,
        "expected_result": "Likely 5-12 more weekday regulars in 6-8 weeks.",
    }


def test_prompt_grounds_in_profile():
    prompt = prompts.build_strategy_prompt(_profile())
    assert "Brew & Bloom Cafe" in prompt
    assert "Cold brew" in prompt
    assert "growing" in prompt
    assert "Hyderabad" in prompt


def test_system_prompt_forbids_invented_numbers():
    assert "NEVER invent numbers" in prompts.SYSTEM_PROMPT


def test_prompt_injects_learned_lessons():
    # Module 6 feedback: learned lessons flow into the strategy prompt.
    block = "LEARNED LESSONS:\n- ✓ [channel] Instagram beats email 2x"
    prompt = prompts.build_strategy_prompt(_profile(), block)
    assert "Instagram beats email 2x" in prompt


def test_prompt_states_when_no_lessons_yet():
    prompt = prompts.build_strategy_prompt(_profile())
    assert "no lessons learned yet" in prompt


@pytest.mark.asyncio
async def test_generate_strategy_calls_llm_with_our_schema(monkeypatch):
    strategy = MarketingStrategy.model_validate(_valid_strategy())
    fake_router = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(data=strategy))
    )
    monkeypatch.setattr(service, "get_llm_router", lambda: fake_router)

    out = await service.generate_strategy(_profile())

    assert out is strategy
    kwargs = fake_router.generate.await_args.kwargs
    assert kwargs["response_schema"] is MarketingStrategy
    assert kwargs["system"] == prompts.SYSTEM_PROMPT
    assert "Brew & Bloom Cafe" in kwargs["messages"][0].content


def test_schema_validates_full_strategy():
    s = MarketingStrategy.model_validate(_valid_strategy())
    assert s.content.priority == "high"
    assert len(s.customer_funnel) == 2


def test_schema_enforces_confidence_bounds():
    bad = _valid_strategy()
    bad["confidence"] = 150
    with pytest.raises(ValidationError):
        MarketingStrategy.model_validate(bad)


def test_schema_requires_all_pillars():
    missing = _valid_strategy()
    del missing["seo"]
    with pytest.raises(ValidationError):
        MarketingStrategy.model_validate(missing)


def test_funnel_stage_is_allowlisted():
    bad = _valid_strategy()
    bad["customer_funnel"][0]["stage"] = "teleportation"
    with pytest.raises(ValidationError):
        MarketingStrategy.model_validate(bad)
