"""Phase 7.20 Stage 3b.4 — Business DNA economics into the Coach analytics summary.

The Analytics Explanation Layer was the one remaining Coach surface without economics
grounding (reality + weekly were done in Stage 3b.1). It now renders the canonical,
provenance-tagged economics facet alongside belief grounding, reusing the SAME shared
accessor (``coach_economics_block`` → ``get_economics_facet``) and the SAME shared
renderer + prompt helpers (``_economics_section`` / ``_ECONOMICS_DISCIPLINE``) as the
other Coach workflows — no new rendering, no second source of truth.

Integration is additive and read-only: belief grounding, the response contract and the
graceful LLM-failure fallback are preserved; a facet miss degrades to an empty block;
the LLM never computes or upgrades an authoritative figure.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_dna.schemas import (
    ContextProvenance,
    DnaFacet,
    DnaItem,
    FacetStatus,
)
from aicmo.modules.business_dna.service import render_economics_block
from aicmo.modules.coach import analytics_summary as summary_mod
from aicmo.modules.coach.analytics_summary import build_analytics_summary
from aicmo.modules.coach.prompts import (
    ANALYTICS_SUMMARY_SYSTEM_PROMPT,
    build_analytics_summary_user_prompt,
)
from aicmo.tenancy.context import TenantContext

# Read-only unit tests: the economics accessor is monkeypatched, so a bare object
# stands in for the DB session at runtime while the cast keeps call sites typed.
_SESSION = cast(AsyncSession, object())


def _profile():
    return cast(
        Any,
        SimpleNamespace(
            business_name="PawPals",
            industry="mobile dog grooming",
            business_location="Austin, TX",
            current_monthly_leads_band="0-10",
            monthly_budget_band="$100-500",
            preferred_platforms=["instagram"],
            target_audience="busy suburban dog owners",
            primary_goal_text="200 bookings/mo",
            brand_id=uuid.uuid4(),
        ),
    )


def _tenant(*, brand: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=brand or uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view"}),
    )


def _facet() -> DnaFacet:
    """Populated facet spanning provenance tiers, carrying currency, a measurement
    period and an explicit INSUFFICIENT_EVIDENCE (evidence-status) item."""
    return DnaFacet(
        key="economics",
        title="Business Economics",
        status=FacetStatus.POPULATED,
        provenance_tiers=[
            ContextProvenance.USER_STATED,
            ContextProvenance.SYSTEM_INFERRED,
        ],
        items=[
            DnaItem(
                label="Unit price",
                detail="65.00 USD",
                provenance=ContextProvenance.USER_STATED,
                source="economics",
            ),
            DnaItem(
                label="Monthly marketing budget",
                detail="1200.00 USD / month",
                provenance=ContextProvenance.USER_STATED,
                source="economics",
            ),
            DnaItem(
                label="Gross margin",
                detail="60.0%",
                provenance=ContextProvenance.SYSTEM_INFERRED,
                source="derived",
            ),
            DnaItem(
                label="Customer acquisition cost (CAC)",
                detail="INSUFFICIENT_EVIDENCE — provide ad spend.",
                provenance=ContextProvenance.UNKNOWN,
                status="insufficient_evidence",
            ),
        ],
        note="economics",
    )


def _composed() -> dict:
    return {
        "signals": ["3 total leads"],
        "overview_dict": {"total_leads": 3, "leads_7d": 1, "conversion_rate": 0.1},
        "timeline_summary": "Window: 30 days. Total: 3.",
        "sources_summary": "(no source data yet)",
        "landing_pages_summary": "(no published landing pages yet)",
        "top_assets_summary": "(no converting assets yet)",
    }


# --------------------------------------------------------------------------- #
#  System prompt — economics discipline present, belief discipline preserved
# --------------------------------------------------------------------------- #


def test_system_prompt_carries_economics_discipline():
    sp = ANALYTICS_SUMMARY_SYSTEM_PROMPT
    assert "BUSINESS ECONOMICS" in sp
    assert "never invent" in sp
    assert "INSUFFICIENT_EVIDENCE metric stays unknown" in sp
    # Learned-belief discipline is still present (preserved, not replaced).
    assert "LEARNED BELIEFS" in sp


# --------------------------------------------------------------------------- #
#  User prompt — included when available; provenance, currency, period kept
# --------------------------------------------------------------------------- #


def _prompt(**over):
    base: dict[str, Any] = dict(
        profile_name="PawPals",
        profile_stage="0-10 band",
        overview={"total_leads": 3},
        timeline_summary="t",
        sources_summary="s",
        landing_pages_summary="lp",
        top_assets_summary="ta",
        belief_block="",
        economics_block="",
    )
    base.update(over)
    return build_analytics_summary_user_prompt(**base)


def test_prompt_includes_economics_with_provenance_currency_and_period():
    block = render_economics_block(_facet())
    prompt = _prompt(economics_block=block)
    assert "# Business economics" in prompt
    # Exact values + provenance tiers + currency + measurement period preserved.
    assert "[USER_STATED] Unit price: 65.00 USD" in prompt
    assert "[USER_STATED] Monthly marketing budget: 1200.00 USD / month" in prompt
    assert "[SYSTEM_INFERRED] Gross margin: 60.0%" in prompt


def test_prompt_insufficient_evidence_not_upgraded():
    prompt = _prompt(economics_block=render_economics_block(_facet()))
    assert "[UNKNOWN] Customer acquisition cost (CAC): INSUFFICIENT_EVIDENCE" in prompt
    assert "[VERIFIED] Customer acquisition cost" not in prompt
    assert "[USER_STATED] Customer acquisition cost" not in prompt


def test_prompt_honest_when_no_economics():
    prompt = _prompt(economics_block="")
    assert "no business economics captured" in prompt


def test_prompt_preserves_belief_grounding_alongside_economics():
    prompt = _prompt(
        belief_block="BELIEF-SENTINEL",
        economics_block=render_economics_block(_facet()),
    )
    assert "BELIEF-SENTINEL" in prompt
    assert "[USER_STATED] Unit price: 65.00 USD" in prompt


# --------------------------------------------------------------------------- #
#  End-to-end: build_analytics_summary threads economics + forwards the tenant
# --------------------------------------------------------------------------- #


class _FakeRouter:
    async def generate(self, *a, **k):
        raise RuntimeError("no LLM in unit test")  # -> graceful fallback


def _patch_common(monkeypatch, *, captured: dict):
    async def _fake_compose(session, *, profile):
        return _composed()

    async def _fake_evidence(session, *, tenant):
        return "BELIEF-BLOCK", None

    def _fake_build(**kwargs):
        captured["economics_block"] = kwargs.get("economics_block")
        captured["belief_block"] = kwargs.get("belief_block")
        return "PROMPT"

    monkeypatch.setattr(summary_mod, "_compose", _fake_compose)
    monkeypatch.setattr(summary_mod, "get_llm_router", lambda: _FakeRouter())
    monkeypatch.setattr(summary_mod, "build_analytics_summary_user_prompt", _fake_build)
    monkeypatch.setattr(
        "aicmo.modules.coach.grounding.resolve_coach_evidence", _fake_evidence
    )


@pytest.mark.asyncio
async def test_build_summary_threads_economics_and_forwards_tenant(monkeypatch):
    captured: dict = {}
    seen: dict = {}

    async def _capture_facet(session, *, tenant):
        seen["tenant"] = tenant
        return _facet()

    _patch_common(monkeypatch, captured=captured)
    # Patch the canonical accessor the coach grounding helper delegates to.
    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _capture_facet
    )

    t = _tenant()
    result = await build_analytics_summary(_SESSION, profile=_profile(), tenant=t)

    # Economics was rendered via the shared renderer and threaded into the prompt.
    assert captured["economics_block"] == render_economics_block(_facet())
    assert "[USER_STATED] Unit price: 65.00 USD" in captured["economics_block"]
    # Brand isolation: the caller's exact tenant reached the brand-scoped accessor.
    assert seen["tenant"] is t
    assert seen["tenant"].brand_id == t.brand_id
    # Belief grounding preserved; response contract intact (fallback still returns a
    # complete AnalyticsSummary).
    assert captured["belief_block"] == "BELIEF-BLOCK"
    assert result.headline
    assert result.signals_used == ["3 total leads"]


@pytest.mark.asyncio
async def test_build_summary_degrades_when_facet_unavailable(monkeypatch):
    captured: dict = {}
    _patch_common(monkeypatch, captured=captured)

    async def _boom(session, *, tenant):
        raise RuntimeError("facet unavailable")

    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _boom
    )

    result = await build_analytics_summary(_SESSION, profile=_profile(), tenant=_tenant())
    # A facet miss degrades to an empty block — the summary is still produced.
    assert captured["economics_block"] == ""
    assert result.headline


@pytest.mark.asyncio
async def test_build_summary_no_economics_without_tenant(monkeypatch):
    """No tenant → no brand → no economics is fetched (no cross-tenant leakage)."""
    captured: dict = {}
    _patch_common(monkeypatch, captured=captured)

    called = {"facet": False}

    async def _should_not_run(session, *, tenant):
        called["facet"] = True
        return _facet()

    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _should_not_run
    )

    result = await build_analytics_summary(_SESSION, profile=_profile(), tenant=None)
    assert captured["economics_block"] == ""
    assert called["facet"] is False
    assert result.headline
