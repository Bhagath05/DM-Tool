"""Phase 7.20 Stage 3b.1 — Business DNA economics integrated into the AI Coach.

The reality + weekly workflows render the canonical economics facet (read-only,
provenance-tagged) alongside belief grounding, with an explicit never-invent /
never-upgrade discipline. Additive: belief grounding and existing behavior are
preserved; a facet failure degrades to an empty block (prompt stays honest).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from aicmo.modules.business_dna.schemas import ContextProvenance, DnaFacet, DnaItem, FacetStatus
from aicmo.modules.coach.prompts import (
    SYSTEM_PROMPT,
    WEEKLY_SYSTEM_PROMPT,
    _economics_section,
    build_user_prompt,
    build_weekly_user_prompt,
)
from aicmo.tenancy.context import TenantContext

_ECON_SENTINEL = "SENTINEL-ECON::unit-price-65"


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        business_name="PawPals", industry="mobile dog grooming", business_location="Austin, TX",
        current_monthly_leads_band="0-10", monthly_budget_band="$100-500",
        preferred_platforms=["instagram"], target_audience="busy suburban dog owners",
        primary_goal_text="200 bookings/mo",
    )


def _tenant(*, brand=None):
    return TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(), organization_id=uuid.uuid4(),
        brand_id=brand or uuid.uuid4(), member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}), permissions=frozenset({"analytics.view"}),
    )


def _facet() -> DnaFacet:
    return DnaFacet(
        key="economics", title="Business Economics", status=FacetStatus.POPULATED,
        provenance_tiers=[ContextProvenance.USER_STATED],
        items=[DnaItem(label="Unit price", detail=_ECON_SENTINEL, provenance=ContextProvenance.USER_STATED, source="economics")],
        note="economics",
    )


# --- system prompts carry the economics discipline (both workflows) ---------


@pytest.mark.parametrize("sp", [SYSTEM_PROMPT, WEEKLY_SYSTEM_PROMPT])
def test_system_prompts_carry_economics_discipline(sp: str):
    assert "BUSINESS ECONOMICS" in sp
    assert "never invent" in sp and "INSUFFICIENT_EVIDENCE metric stays unknown" in sp
    # The learned-belief discipline is still present (preserved, not replaced).
    assert "LEARNED BELIEFS" in sp


# --- the section renders the block, or an honest absence note ---------------


def test_economics_section_renders_block_and_absence():
    assert _ECON_SENTINEL in _economics_section(_ECON_SENTINEL)
    assert "no business economics captured" in _economics_section("")


# --- both user-prompt builders inject the economics block additively --------


def test_reality_prompt_injects_economics_and_preserves_beliefs():
    prompt = build_user_prompt(
        profile=_profile(), goal_text="get 20 leads", timeline_hint="3 months",
        feasibility_score=55, feasibility_label="Aggressive but possible", signals=[],
        belief_block="BELIEF-SENTINEL", economics_block=_ECON_SENTINEL,
    )
    assert _ECON_SENTINEL in prompt and "BELIEF-SENTINEL" in prompt  # both grounded


def test_weekly_prompt_injects_economics_and_preserves_beliefs():
    prompt = build_weekly_user_prompt(
        profile=_profile(), signals=[], recent_activity={}, has_published_page=False,
        top_asset_summary=None, trends_summary=None, analysis_phase_summary=None,
        analysis_channels=[], belief_block="BELIEF-SENTINEL", economics_block=_ECON_SENTINEL,
    )
    assert _ECON_SENTINEL in prompt and "BELIEF-SENTINEL" in prompt


def test_prompts_honest_when_no_economics():
    prompt = build_user_prompt(
        profile=_profile(), goal_text="x", timeline_hint=None, feasibility_score=50,
        feasibility_label="Aggressive but possible", signals=[], belief_block="", economics_block="",
    )
    assert "no business economics captured" in prompt


# --- coach_economics_block: facet consumption, degrade, empty ---------------


@pytest.mark.asyncio
async def test_coach_economics_block_renders_facet_with_provenance(monkeypatch):
    from aicmo.modules.coach import grounding

    async def _fake_facet(session, *, tenant):
        return _facet()

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _fake_facet)
    block = await grounding.coach_economics_block(None, tenant=_tenant())
    assert _ECON_SENTINEL in block and "[USER_STATED] Unit price:" in block


@pytest.mark.asyncio
async def test_coach_economics_block_degrades_to_empty_on_failure(monkeypatch):
    from aicmo.modules.coach import grounding

    async def _boom(session, *, tenant):
        raise RuntimeError("facet unavailable")

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _boom)
    assert await grounding.coach_economics_block(None, tenant=_tenant()) == ""


@pytest.mark.asyncio
async def test_coach_economics_block_empty_when_no_items(monkeypatch):
    from aicmo.modules.coach import grounding

    async def _empty(session, *, tenant):
        return DnaFacet(key="economics", title="Business Economics", status=FacetStatus.UNKNOWN,
                        provenance_tiers=[ContextProvenance.UNKNOWN], items=[], note="")

    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _empty)
    assert await grounding.coach_economics_block(None, tenant=_tenant()) == ""
