"""Phase 6.3 (Gap B) — AI creative brief is GROUNDED, tenant-scoped, and
refuses to fabricate. Hermetic: the LLM router + context fetches are stubbed,
so no network + no DB.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.creative import brief_service
from aicmo.modules.creative.brief_schemas import CreativeBriefResult
from aicmo.modules.creative.models import CreativeBrief

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="u-1", user_uuid=uuid.uuid4()
)

_PROFILE = SimpleNamespace(
    business_name="Bean & Brew", industry="Cafe", target_audience="local commuters",
    brand_tone="warm", business_location="Austin", unique_selling_points=["single-origin"],
    services=["espresso", "pastries"], preferred_platforms=["Instagram"],
    primary_goal_text="more foot traffic",
)

_BRIEF_RESULT = CreativeBriefResult(
    objective="Drive foot traffic", audience="local commuters",
    key_message="Best morning espresso in Austin", tone="warm",
    visual_direction="warm morning light, steam, wood tones",
    must_include=["logo"], avoid=["stock clichés"], deliverables=["poster", "story"],
    confidence=82, reason="business profile + active strategy",
)


class _FakeSession:
    """Captures adds; scalar/execute return stubbed context rows."""

    def __init__(self, *, strategy=None):
        self.added: list = []
        self._strategy = strategy

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass

    async def execute(self, _stmt):
        # only used by _latest_strategy in these tests
        return SimpleNamespace(scalar_one_or_none=lambda: self._strategy)

    async def scalar(self, _stmt):  # campaign/content lookups (unused here)
        return None


@pytest.fixture(autouse=True)
def _stub_llm_and_profile(monkeypatch):
    async def _fake_generate(**_kwargs):
        return SimpleNamespace(data=_BRIEF_RESULT)

    monkeypatch.setattr(
        brief_service, "get_llm_router",
        lambda: SimpleNamespace(generate=_fake_generate),
    )

    async def _fake_profile(_session, _brand_id):
        return _PROFILE

    monkeypatch.setattr(
        brief_service.onboarding_service, "get_profile_or_none", _fake_profile
    )

    async def _no_audit(*_a, **_k):
        return None

    monkeypatch.setattr(brief_service.audit_service, "record", _no_audit)


def test_generates_grounded_brief_and_persists():
    session = _FakeSession()
    row = asyncio.run(
        brief_service.generate_brief(
            session, tenant=_TENANT, objective="Drive foot traffic"
        )
    )
    assert isinstance(row, CreativeBrief)
    assert row.organization_id == _ORG and row.brand_id == _BRAND
    assert row.confidence == 82
    assert row.grounded_in == ["business profile"]  # no strategy provided
    assert row.brief["key_message"] == "Best morning espresso in Austin"
    assert "poster" in row.brief["deliverables"]


def test_includes_strategy_when_present():
    strategy = SimpleNamespace(id=uuid.uuid4(), strategy={"audience": "commuters"})
    session = _FakeSession(strategy=strategy)
    row = asyncio.run(brief_service.generate_brief(session, tenant=_TENANT))
    assert "active strategy" in row.grounded_in
    assert row.strategy_id == strategy.id


def test_refuses_without_business_profile(monkeypatch):
    async def _no_profile(_session, _brand_id):
        return None

    monkeypatch.setattr(
        brief_service.onboarding_service, "get_profile_or_none", _no_profile
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(brief_service.generate_brief(_FakeSession(), tenant=_TENANT))
    assert ei.value.status_code == 409  # grounding required, never fabricated


def test_requires_a_brand():
    no_brand = SimpleNamespace(
        organization_id=_ORG, brand_id=None, user_id="u", user_uuid=uuid.uuid4()
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(brief_service.generate_brief(_FakeSession(), tenant=no_brand))
    assert ei.value.status_code == 400
