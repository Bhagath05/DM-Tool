"""Phase 3.3 — Planner unit tests (no DB; mocked LLM router)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from aicmo.modules.planner import prompts, service
from aicmo.modules.planner.schemas import DailyPlan
from aicmo.modules.strategist.schemas import MarketingStrategy


def _profile(**over):
    base = dict(
        business_name="Brew & Bloom Cafe",
        industry="Specialty coffee shop",
        growth_stage="growing",
        preferred_platforms=["instagram"],
        primary_goal_text="Get 50 new customers this month",
        goals=["More walk-ins"],
        monthly_budget_band="₹10k-25k",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _pillar(focus="X"):
    return {"focus": focus, "why": "fits", "actions": ["do a"], "priority": "medium"}


def _strategy() -> MarketingStrategy:
    period = {"period": "This week", "focus": "reels launch", "milestones": ["Post 3 reels"]}
    return MarketingStrategy.model_validate(
        {
            "positioning": "Cozy specialty cafe for remote workers.",
            "target_summary": "Remote workers who value calm + coffee.",
            "content": _pillar("reels"),
            "seo": _pillar(),
            "local_seo": _pillar(),
            "paid_ads": _pillar(),
            "organic_social": _pillar(),
            "email": _pillar(),
            "influencer": _pillar(),
            "customer_funnel": [{"stage": "awareness", "goal": "be found", "tactics": ["reels"]}],
            "campaign_roadmap": ["Grand-opening push"],
            "weekly_plan": period,
            "monthly_plan": {**period, "period": "Month 1"},
            "quarterly_plan": {**period, "period": "Q1"},
            "recommendation": "Launch a weekday loyalty card.",
            "reason": "Seating is the edge.",
            "confidence": 70,
            "expected_result": "5-12 more regulars in 6-8 weeks.",
        }
    )


def _valid_plan():
    return {
        "summary": "Kick off this week's reel push.",
        "focus": "Get the first grand-opening reel out.",
        "tasks": [
            {
                "title": "Post a 60-second reel about your cold brew",
                "category": "content",
                "why": "This week's milestone is 3 reels; start with the hero product.",
                "priority": "high",
                "effort": "medium",
                "suggested_action": "Content Studio → reel",
            }
        ],
    }


def test_prompt_grounds_in_strategy():
    prompt = prompts.build_plan_prompt(_profile(), _strategy())
    assert "Cozy specialty cafe" in prompt
    assert "reels launch" in prompt  # this week's focus
    assert "Post 3 reels" in prompt  # milestone


def test_prompt_without_strategy_nudges_to_generate_one():
    prompt = prompts.build_plan_prompt(_profile(), None)
    assert "no marketing strategy yet" in prompt


@pytest.mark.asyncio
async def test_generate_daily_plan_calls_llm_with_our_schema(monkeypatch):
    plan = DailyPlan.model_validate(_valid_plan())
    fake_router = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(data=plan))
    )
    monkeypatch.setattr(service, "get_llm_router", lambda: fake_router)

    out = await service.generate_daily_plan(_profile(), _strategy())

    assert out is plan
    kwargs = fake_router.generate.await_args.kwargs
    assert kwargs["response_schema"] is DailyPlan
    assert kwargs["system"] == prompts.SYSTEM_PROMPT


def test_plan_schema_validates():
    p = DailyPlan.model_validate(_valid_plan())
    assert p.tasks[0].category == "content"
    assert p.tasks[0].priority == "high"


@pytest.mark.parametrize(
    "field,bad",
    [("category", "teleport"), ("priority", "urgent"), ("effort", "epic")],
)
def test_plan_task_allowlists(field, bad):
    payload = _valid_plan()
    payload["tasks"][0][field] = bad
    with pytest.raises(ValidationError):
        DailyPlan.model_validate(payload)
