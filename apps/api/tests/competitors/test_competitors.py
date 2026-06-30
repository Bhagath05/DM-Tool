"""Competitor-intelligence unit tests.

Lightweight by design: the pure logic (prompt building, the LLM call,
schema validation) is exercised with a duck-typed profile and a mocked
LLM router — no database, no app bootstrap.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from aicmo.modules.competitors import prompts, service
from aicmo.modules.competitors.schemas import (
    CompetitorAnalysisResponse,
    CompetitorInsight,
)


def _profile(**overrides):
    base = dict(
        business_name="Brew & Bloom",
        industry="Specialty coffee shop",
        brand_tone="warm",
        target_audience="Local remote workers and students who value good coffee",
        preferred_platforms=["instagram", "facebook"],
        goals=["Get more walk-in customers", "Build a loyal regulars base"],
        competitors=["Roasted Down the Road", "Bean Counter Cafe"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _valid_response_dict():
    return {
        "market_summary": "Customers choose on vibe and consistency.",
        "competitors": [
            {
                "name": "Roasted Down the Road",
                "positioning": "Fast, cheap, grab-and-go.",
                "strengths": ["Speed", "Price"],
                "gaps": ["No seating to linger"],
                "content_angles": ["Daily deal posts"],
                "your_move": "Lean into a cozy work-friendly space they can't match.",
                "confidence": 70,
            }
        ],
        "recommendation": "Launch a 'stay and work' loyalty card for weekday mornings.",
        "reason": "Your seating + audience of remote workers is the clearest edge.",
        "confidence": 72,
        "expected_result": "Likely 5-12 more weekday regulars within 6-8 weeks.",
    }


def test_build_user_prompt_lists_every_named_competitor():
    prompt = prompts.build_user_prompt(_profile())
    assert "Roasted Down the Road" in prompt
    assert "Bean Counter Cafe" in prompt
    assert "Brew & Bloom" in prompt
    # The honesty + one-per-name contract must reach the model.
    assert "one entry in `competitors` for EACH" in prompt


def test_system_prompt_forbids_invented_numbers():
    assert "NEVER invent specific numbers" in prompts.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_analyze_calls_llm_router_with_our_schema_and_returns_data(monkeypatch):
    resp = CompetitorAnalysisResponse.model_validate(_valid_response_dict())
    fake_router = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(data=resp)),
    )
    monkeypatch.setattr(service, "get_llm_router", lambda: fake_router)

    out = await service.analyze(_profile())

    assert out is resp
    fake_router.generate.assert_awaited_once()
    kwargs = fake_router.generate.await_args.kwargs
    assert kwargs["response_schema"] is CompetitorAnalysisResponse
    assert kwargs["system"] == prompts.SYSTEM_PROMPT
    assert "Roasted Down the Road" in kwargs["messages"][0].content


@pytest.mark.asyncio
async def test_analyze_competitors_raises_when_no_competitors(monkeypatch):
    profile_row = object()
    monkeypatch.setattr(
        service.onboarding_service,
        "get_profile_or_none",
        AsyncMock(return_value=profile_row),
    )
    monkeypatch.setattr(
        service.BusinessProfileResponse,
        "model_validate",
        classmethod(lambda cls, _row: _profile(competitors=[])),
    )

    with pytest.raises(service.NoCompetitors):
        await service.analyze_competitors(session=None, brand_id="b1")


@pytest.mark.asyncio
async def test_analyze_competitors_raises_when_profile_missing(monkeypatch):
    monkeypatch.setattr(
        service.onboarding_service,
        "get_profile_or_none",
        AsyncMock(return_value=None),
    )
    with pytest.raises(service.ProfileMissing):
        await service.analyze_competitors(session=None, brand_id="b1")


def test_response_schema_enforces_confidence_bounds():
    bad = _valid_response_dict()
    bad["confidence"] = 150
    with pytest.raises(ValidationError):
        CompetitorAnalysisResponse.model_validate(bad)


def test_response_schema_requires_recommendation_contract():
    missing = _valid_response_dict()
    del missing["recommendation"]
    with pytest.raises(ValidationError):
        CompetitorAnalysisResponse.model_validate(missing)


def test_insight_requires_confidence():
    with pytest.raises(ValidationError):
        CompetitorInsight.model_validate(
            {
                "name": "X",
                "positioning": "y",
                "your_move": "z",
                # confidence missing
            }
        )
