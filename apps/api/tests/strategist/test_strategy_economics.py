"""Phase 7.20 Stage 3b.2 — Business DNA economics integrated into Strategy.

The strategy generation + refresh workflow receives the canonical, provenance-
tagged Business Economics block (reusing the shared accessor + renderer), with an
explicit never-invent/never-upgrade discipline. Additive: belief grounding,
generation, refresh and API behavior are preserved; a facet failure degrades to
an empty block (the prompt stays honest).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from aicmo.modules.business_dna.schemas import ContextProvenance, DnaFacet, DnaItem, FacetStatus
from aicmo.modules.business_dna.service import render_economics_block
from aicmo.modules.strategist import prompts, service
from aicmo.modules.strategist.grounding import resolve_strategy_economics
from aicmo.modules.strategist.prompts import SYSTEM_PROMPT, build_strategy_prompt
from aicmo.tenancy.context import TenantContext

_ECON_SENTINEL = "SENTINEL-ECON::unit-price-65-USD"


def _tenant(*, brand=None):
    return TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(), organization_id=uuid.uuid4(),
        brand_id=brand or uuid.uuid4(), member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}), permissions=frozenset({"content.create"}),
    )


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        business_name="PawPals", industry="mobile dog grooming", business_type="service",
        products=["Full groom"], services=["Bath"], unique_selling_points=["Comes to you"],
        competitors=[], goals=["grow memberships"], preferred_platforms=["instagram"],
        pricing="$65 full groom", growth_stage=None, business_location="Austin, TX",
        target_audience="busy suburban dog owners", current_monthly_leads_band="0-10",
        monthly_budget_band="$100-500", brand_tone="friendly",
        primary_goal_text="200 bookings/mo", analysis=None,
    )


def _facet(*, populated=True) -> DnaFacet:
    if not populated:
        return DnaFacet(key="economics", title="Business Economics", status=FacetStatus.UNKNOWN,
                        provenance_tiers=[ContextProvenance.UNKNOWN], items=[], note="")
    return DnaFacet(
        key="economics", title="Business Economics", status=FacetStatus.POPULATED,
        provenance_tiers=[ContextProvenance.USER_STATED, ContextProvenance.SYSTEM_INFERRED],
        items=[
            DnaItem(label="Unit price", detail=f"65.00 USD ({_ECON_SENTINEL})", provenance=ContextProvenance.USER_STATED, source="economics"),
            DnaItem(label="Gross margin", detail="60.0%", provenance=ContextProvenance.SYSTEM_INFERRED, source="derived"),
            DnaItem(label="Customer acquisition cost (CAC)", detail="INSUFFICIENT_EVIDENCE — provide spend.", provenance=ContextProvenance.UNKNOWN, status="insufficient_evidence"),
        ],
        note="economics",
    )


# --- system prompt discipline ----------------------------------------------


def test_system_prompt_carries_economics_discipline():
    assert "BUSINESS ECONOMICS" in SYSTEM_PROMPT
    assert "never invent" in SYSTEM_PROMPT and "INSUFFICIENT_EVIDENCE metric stays unknown" in SYSTEM_PROMPT
    # Belief-grounding discipline preserved (not replaced).
    assert "LEARNED EVIDENCE" in SYSTEM_PROMPT


# --- prompt injection (generation context) ---------------------------------


def test_build_strategy_prompt_injects_economics_and_preserves_beliefs():
    prompt = build_strategy_prompt(_profile(), "", "", "BELIEF-SENTINEL", _ECON_SENTINEL)
    assert _ECON_SENTINEL in prompt and "BELIEF-SENTINEL" in prompt
    assert "# Business economics" in prompt


def test_build_strategy_prompt_honest_when_no_economics():
    prompt = build_strategy_prompt(_profile(), "", "", "", "")
    assert "no business economics captured" in prompt


# --- generate_strategy forwards economics_block to the prompt builder -------


@pytest.mark.asyncio
async def test_generate_strategy_forwards_economics_block(monkeypatch):
    captured: dict = {}

    def _fake_build(profile, learning_block="", goals_block="", belief_block="", economics_block=""):
        captured["economics_block"] = economics_block
        return "PROMPT"

    class _FakeRouter:
        async def generate(self, **kw):
            return SimpleNamespace(data="STRATEGY")

    monkeypatch.setattr(prompts, "build_strategy_prompt", _fake_build)
    monkeypatch.setattr(service, "get_llm_router", lambda: _FakeRouter())
    await service.generate_strategy(_profile(), "", "", "BELIEF", _ECON_SENTINEL)
    assert captured["economics_block"] == _ECON_SENTINEL


# --- run_strategy (refresh/background) threads economics_block --------------


@pytest.mark.asyncio
async def test_run_strategy_threads_economics_block(monkeypatch):
    captured: dict = {}

    async def _fake_generate(snapshot, learning_block="", goals_block="", belief_block="", economics_block=""):
        captured["economics_block"] = economics_block
        return SimpleNamespace(model_dump=lambda: {})

    class _DummyCM:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *a):
            return False

    async def _noop_finish(*a, **k):
        return None

    monkeypatch.setattr(service, "generate_strategy", _fake_generate)
    monkeypatch.setattr(service, "SessionLocal", lambda: _DummyCM())
    monkeypatch.setattr(service, "_finish", _noop_finish)
    await service.run_strategy(str(uuid.uuid4()), _profile(), "", "", "BELIEF", None, economics_block=_ECON_SENTINEL)
    assert captured["economics_block"] == _ECON_SENTINEL


# --- resolve_strategy_economics: delegation, provenance, degrade ------------


@pytest.mark.asyncio
async def test_resolve_strategy_economics_renders_provenance(monkeypatch):
    async def _fake_facet(session, *, tenant):
        return _facet()

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _fake_facet)
    block = await resolve_strategy_economics(None, tenant=_tenant())
    assert _ECON_SENTINEL in block
    assert "[USER_STATED] Unit price:" in block and "[SYSTEM_INFERRED] Gross margin: 60.0%" in block
    assert "INSUFFICIENT_EVIDENCE" in block  # the uncomputable CAC stays unknown


@pytest.mark.asyncio
async def test_resolve_strategy_economics_degrades_to_empty(monkeypatch):
    async def _boom(session, *, tenant):
        raise RuntimeError("facet unavailable")

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _boom)
    assert await resolve_strategy_economics(None, tenant=_tenant()) == ""


@pytest.mark.asyncio
async def test_resolve_strategy_economics_empty_when_no_items(monkeypatch):
    async def _empty(session, *, tenant):
        return _facet(populated=False)

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _empty)
    assert await resolve_strategy_economics(None, tenant=_tenant()) == ""


# --- shared renderer parity (Coach + Strategy use the same one) -------------


def test_render_economics_block_shared_renderer():
    block = render_economics_block(_facet())
    assert "[USER_STATED] Unit price:" in block
    assert render_economics_block(_facet(populated=False)) == ""
