"""Phase B.1 — migrated product call sites pass typed LLM tasks.

Hermetic: mocks at the LLM router boundary. No network, no real providers.
"""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.advisor import intelligence
from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.schemas import DataSourceRef, ExecuteRecommendationRequest
from aicmo.modules.advisor.signals import IntelligenceSignals
from aicmo.modules.content import generator as content_generator
from aicmo.modules.creative import brief_service
from aicmo.modules.creative.brief_schemas import CreativeBriefResult
from aicmo.modules.creative.models import CreativeBrief
from aicmo.modules.growth import strategy as growth_strategy
from aicmo.modules.marketing_analytics.schemas import AdvisorAnalyticsSignal
from aicmo.modules.planner import service as planner_service
from aicmo.modules.planner.schemas import DailyPlan
from aicmo.modules.strategist import service as strategist_service
from aicmo.modules.strategist.schemas import MarketingStrategy
from aicmo.modules.trends import analyzer as trends_analyzer
from aicmo.tenancy.context import TenantContext


def _tenant() -> TenantContext:
    return TenantContext(
        user_id="u",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
    )


def _strategy_payload() -> dict:
    pillar = {"focus": "reels", "why": "fits", "actions": ["do a"], "priority": "high"}
    period = {"period": "This week", "focus": "launch", "milestones": ["m1", "m2", "m3"]}
    return {
        "positioning": "A cozy specialty cafe for remote workers.",
        "target_summary": "Local remote workers who value quality + calm.",
        "content": pillar,
        "seo": pillar,
        "local_seo": pillar,
        "paid_ads": pillar,
        "organic_social": pillar,
        "email": pillar,
        "influencer": pillar,
        "customer_funnel": [
            {"stage": "awareness", "goal": "be discovered", "tactics": ["reels"]},
        ],
        "campaign_roadmap": ["Grand-opening push"],
        "weekly_plan": period,
        "monthly_plan": {**period, "period": "Month 1"},
        "quarterly_plan": {**period, "period": "Q1"},
        "recommendation": "Launch a weekday loyalty card.",
        "reason": "Seating + remote-worker audience is the clearest edge.",
        "confidence": 74,
        "expected_result": "Likely 5-12 more weekday regulars in 6-8 weeks.",
    }


def _profile(**over):
    base = dict(
        business_name="Brew & Bloom Cafe",
        industry="Cafe",
        business_type="cafe",
        products=["Cold brew"],
        services=[],
        unique_selling_points=["Single-origin"],
        pricing="Premium",
        growth_stage="growing",
        business_location="Hyderabad",
        target_audience="Remote workers",
        current_monthly_leads_band="10-50",
        monthly_budget_band="₹10k-25k",
        brand_tone="warm",
        primary_goal_text="Get customers",
        goals=["More walk-ins"],
        preferred_platforms=["instagram"],
        competitors=[],
        analysis=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_advisor_intelligence_passes_intelligence_task(monkeypatch):
    captured: dict = {}

    class _Router:
        async def generate(self, **kw):
            captured.update(kw)
            raise RuntimeError("intentional llm failure for task capture")

    ctx = IntelligenceSignals(
        brain=BusinessBrain(
            industry="Cafe",
            business_type="Coffee",
            target_audience="Pros",
            business_name="Brew",
            preferred_platforms=["Instagram"],
        ),
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={"metrics": [], "has_data": False},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 1"],
        data_sources=[DataSourceRef(key="x", label="x", value="1")],
        has_connectors=False,
        activity_signals=2,
        analytics_signal=AdvisorAnalyticsSignal(
            has_data=False,
            connected=True,
            data_sufficiency="none",
            window="7d",
            headline="hi",
            content_insights=[],
        ),
    )
    monkeypatch.setattr(intelligence, "gather_intelligence_signals", AsyncMock(return_value=ctx))
    monkeypatch.setattr(intelligence, "get_llm_router", lambda: _Router())
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(
            advisor_intelligence_enabled=True,
            advisor_engine_enabled=False,
        ),
    )
    monkeypatch.setattr(
        intelligence.analytics_service,
        "overview",
        AsyncMock(
            return_value=SimpleNamespace(
                total_leads=1,
                hot_leads=0,
                leads_7d=1,
                total_spend=0,
            )
        ),
    )

    report = await intelligence.compose_intelligence(
        SimpleNamespace(),
        profile=SimpleNamespace(),
        tenant=_tenant(),
    )
    assert captured["task"] == "intelligence"
    # Deterministic fallback still works when LLM fails.
    assert report.ready is True or report.empty is not None or report.hero is not None


@pytest.mark.asyncio
async def test_strategist_passes_strategy_reasoning(monkeypatch):
    strategy = MarketingStrategy.model_validate(_strategy_payload())
    fake = SimpleNamespace(generate=AsyncMock(return_value=SimpleNamespace(data=strategy)))
    monkeypatch.setattr(strategist_service, "get_llm_router", lambda: fake)
    await strategist_service.generate_strategy(_profile())
    assert fake.generate.await_args.kwargs["task"] == "strategy_reasoning"


@pytest.mark.asyncio
async def test_planner_passes_strategy_reasoning(monkeypatch):
    plan = DailyPlan.model_validate(
        {
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
    )
    fake = SimpleNamespace(generate=AsyncMock(return_value=SimpleNamespace(data=plan)))
    monkeypatch.setattr(planner_service, "get_llm_router", lambda: fake)
    await planner_service.generate_daily_plan(_profile(), strategy=None)
    assert fake.generate.await_args.kwargs["task"] == "strategy_reasoning"


@pytest.mark.asyncio
async def test_growth_strategy_passes_strategy_reasoning(monkeypatch):
    captured: dict = {}

    class _Router:
        async def generate(self, **kw):
            captured.update(kw)
            raise RuntimeError("stop after capture")

    monkeypatch.setattr(growth_strategy, "get_llm_router", lambda: _Router())
    objective = SimpleNamespace(
        objective_kind="get_leads",
        statement="I need more qualified leads this month",
        audience_hypothesis="Local remote workers",
        brand_id=uuid.uuid4(),
    )
    with pytest.raises(RuntimeError, match="stop after capture"):
        await growth_strategy._llm_plan(
            objective,
            "lead",
            ["instagram"],
            "business_name: Brew\nindustry: Cafe",
        )
    assert captured["task"] == "strategy_reasoning"


@pytest.mark.asyncio
async def test_content_generator_passes_creative_generation(monkeypatch):
    captured: dict = {}

    class _Router:
        async def generate(self, **kw):
            captured.update(kw)
            raise RuntimeError("stop after capture")

    monkeypatch.setattr(content_generator, "get_llm_router", lambda: _Router())
    with pytest.raises(RuntimeError, match="stop after capture"):
        await content_generator.generate_content(
            content_type="social_post",
            profile=_profile(),
            trend_analysis=None,
            platform="instagram",
            goal="leads",
            tone_override=None,
        )
    assert captured["task"] == "creative_generation"


@pytest.mark.asyncio
async def test_creative_brief_passes_creative_generation(monkeypatch):
    result = CreativeBriefResult(
        objective="Drive foot traffic",
        audience="local commuters",
        key_message="Best morning espresso",
        tone="warm",
        visual_direction="warm light",
        must_include=["logo"],
        avoid=["clichés"],
        deliverables=["poster"],
        confidence=82,
        reason="business profile",
    )
    captured: dict = {}

    async def _fake_generate(**kw):
        captured.update(kw)
        return SimpleNamespace(data=result)

    monkeypatch.setattr(
        brief_service,
        "get_llm_router",
        lambda: SimpleNamespace(generate=_fake_generate),
    )
    monkeypatch.setattr(
        brief_service.onboarding_service,
        "get_profile_or_none",
        AsyncMock(return_value=_profile()),
    )
    monkeypatch.setattr(brief_service.audit_service, "record", AsyncMock(return_value=None))

    class _FakeSession:
        def __init__(self):
            self.added: list = []

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

        async def execute(self, _stmt):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        async def scalar(self, _stmt):
            return None

    row = await brief_service.generate_brief(
        _FakeSession(),
        tenant=_tenant(),
        objective="Drive foot traffic",
    )
    assert isinstance(row, CreativeBrief)
    assert captured["task"] == "creative_generation"


@pytest.mark.asyncio
async def test_trends_analyzer_remains_without_task():
    """Non-migrated call sites stay on global defaults (no task=)."""
    src = inspect.getsource(trends_analyzer.run_refresh)
    assert "task=" not in src
    assert "get_llm_router" in src


def test_api_request_schemas_cannot_select_task_or_provider():
    """User/API input must not carry task/provider/model selection knobs."""
    assert "task" not in ExecuteRecommendationRequest.model_fields
    assert "provider" not in ExecuteRecommendationRequest.model_fields
    assert "model" not in ExecuteRecommendationRequest.model_fields

    sig = inspect.signature(intelligence.compose_intelligence)
    assert "task" not in sig.parameters
    assert "provider" not in sig.parameters
    assert "model" not in sig.parameters


def test_agent_reasoning_unused_by_design():
    """No Jarvis/tool agent yet — agent_reasoning must not be forced onto call sites."""
    from aicmo.modules.advisor import agent as advisor_agent

    src = inspect.getsource(advisor_agent)
    assert 'task="agent_reasoning"' not in src
    assert 'task="intelligence"' in src
