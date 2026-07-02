"""Phase 3.5 — Decision Engine unit tests (no DB; mocked LLM router)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from aicmo.modules.decision_engine import prompts, service
from aicmo.modules.decision_engine.schemas import DecisionReport, DecisionSignals


def _signals(**over) -> DecisionSignals:
    base = dict(
        has_profile=True,
        business_name="Brew & Bloom Cafe",
        industry="Specialty coffee shop",
        growth_stage="growing",
        primary_goal="Get 50 new customers this month",
        goals=["More walk-ins"],
        competitors=["Roasted Down the Road"],
        total_leads=42,
        leads_7d=8,
        leads_30d=25,
        hot_leads=5,
        total_views=1200,
        conversion_rate=0.035,
        landing_pages_published=2,
        performance_has_data=False,
        scheduled_posts=3,
        published_posts=10,
        failed_posts=1,
        has_strategy=True,
        strategy_top_move="Launch a weekday loyalty card",
    )
    base.update(over)
    return DecisionSignals(**base)


def _valid_report():
    return {
        "decisions": [
            {
                "decision": "Double down on Instagram reels this week.",
                "reasoning": "Leads are flowing but views→leads conversion is low.",
                "evidence": ["42 total leads, 8 in the last 7 days", "conversion 3.5%"],
                "expected_impact": "Likely 3-8 more leads over 2 weeks.",
                "confidence": 65,
                "urgency": "this_week",
                "recommended_action": "Publish 3 reels tied to the loyalty card.",
                "alternative_actions": ["Run a small geo-targeted ad test"],
                "risks": ["Reels take production time"],
                "business_objective": "Get 50 new customers this month",
                "affected_channels": ["instagram"],
            }
        ],
        "data_sufficiency": "Moderate — leads + publishing present; no performance CSV yet.",
    }


def test_prompt_quotes_real_numbers():
    prompt = prompts.build_decision_prompt(_signals(total_leads=42, leads_7d=8))
    assert "42" in prompt
    assert "8" in prompt
    assert "Brew & Bloom Cafe" in prompt


def test_prompt_without_profile_points_to_onboarding():
    prompt = prompts.build_decision_prompt(_signals(has_profile=False))
    assert "No business profile" in prompt


def test_system_prompt_forbids_fabrication():
    assert "do NOT invent" in prompts.SYSTEM_PROMPT
    assert "too thin" in prompts.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_decide_from_signals_calls_llm_with_our_schema(monkeypatch):
    report = DecisionReport.model_validate(_valid_report())
    fake_router = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(data=report))
    )
    monkeypatch.setattr(service, "get_llm_router", lambda: fake_router)

    out = await service.decide_from_signals(_signals())

    assert out is report
    kwargs = fake_router.generate.await_args.kwargs
    assert kwargs["response_schema"] is DecisionReport
    assert kwargs["system"] == prompts.SYSTEM_PROMPT
    assert "42" in kwargs["messages"][0].content  # real evidence reached the model


def test_decision_schema_validates():
    r = DecisionReport.model_validate(_valid_report())
    d = r.decisions[0]
    assert d.urgency == "this_week"
    assert d.evidence and d.business_objective


def test_decision_confidence_bounds():
    bad = _valid_report()
    bad["decisions"][0]["confidence"] = 200
    with pytest.raises(ValidationError):
        DecisionReport.model_validate(bad)


def test_decision_urgency_allowlist():
    bad = _valid_report()
    bad["decisions"][0]["urgency"] = "immediately"
    with pytest.raises(ValidationError):
        DecisionReport.model_validate(bad)
