"""Phase 7.20 Stage 3b.3 — Business DNA economics into Opportunity Intelligence.

The legacy Opportunity Center narrative path grounds its prompt in the canonical,
provenance-tagged Business Economics facet (the unified-intelligence path already
carries it via the advisor signals, Stage 3). Integration is additive and read-only:

- ``resolve_opportunity_economics`` reuses the canonical facet accessor + the shared
  renderer (no duplicate calculation, no second source of truth) and degrades to ""
  so a facet miss never aborts the report.
- The prompt renders every figure EXACTLY as given with an explicit never-invent /
  never-upgrade discipline; an INSUFFICIENT_EVIDENCE metric stays unknown; financial
  context alone never fabricates an opportunity.
- Brand isolation is inherited from the brand-scoped accessor; the resolver forwards
  the caller's TenantContext unchanged.
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
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.opportunities import center
from aicmo.modules.opportunities.center import resolve_opportunity_economics
from aicmo.modules.opportunities.prompts import (
    OPPORTUNITY_SYSTEM_PROMPT,
    build_opportunity_user_prompt,
)
from aicmo.tenancy.context import TenantContext

# A typed stand-in for the DB session: these unit tests never touch the DB (the
# economics accessor is monkeypatched), so a bare object satisfies the read-only
# contract at runtime while the cast keeps the typed call sites honest.
_SESSION = cast(AsyncSession, object())

# --------------------------------------------------------------------------- #
#  Fixtures / helpers
# --------------------------------------------------------------------------- #


def _profile() -> BusinessProfileResponse:
    # Attribute-compatible stand-in — the prompt builder only reads these fields.
    return cast(
        BusinessProfileResponse,
        SimpleNamespace(
            business_name="Brew & Bloom",
            industry="Cafe",
            business_location="Hyderabad",
            primary_goal_text="More leads",
            current_monthly_leads_band="10-50",
            monthly_budget_band="low",
            preferred_platforms=["instagram"],
            target_audience="Remote workers who want specialty coffee",
        ),
    )


def _kwargs(*, economics_block=None, belief_block=None) -> dict[str, Any]:
    return dict(
        profile=_profile(),
        counts_block="(none)",
        top_source_summary=None,
        top_asset_summary=None,
        trends_summary=None,
        recent_content_summary=None,
        recent_ads_summary=None,
        signals=[],
        memory_block=None,
        belief_block=belief_block,
        economics_block=economics_block,
    )


def _econ_facet() -> DnaFacet:
    """A populated economics facet carrying currency, a measurement period and an
    explicit INSUFFICIENT_EVIDENCE (evidence-status) item across provenance tiers."""
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


def _tenant(brand_id: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=brand_id or uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view"}),
    )


# --------------------------------------------------------------------------- #
#  1 + 3. Economics context included when available; provenance + currency kept
# --------------------------------------------------------------------------- #


def test_prompt_includes_economics_when_available():
    block = render_economics_block(_econ_facet())
    prompt = build_opportunity_user_prompt(**_kwargs(economics_block=block))
    assert "# Business economics" in prompt
    # Figures appear EXACTLY as given — currency, period and provenance tier kept.
    assert "[USER_STATED] Unit price: 65.00 USD" in prompt
    assert "[USER_STATED] Monthly marketing budget: 1200.00 USD / month" in prompt
    assert "[SYSTEM_INFERRED] Gross margin: 60.0%" in prompt


# --------------------------------------------------------------------------- #
#  2. Missing economics → honest insufficient-evidence context
# --------------------------------------------------------------------------- #


def test_prompt_states_absent_economics_honestly():
    prompt = build_opportunity_user_prompt(**_kwargs(economics_block=None))
    assert "# Business economics" in prompt
    assert "no business economics captured" in prompt
    # No fabricated figures — the model is told not to assume any.
    assert "do not assume" in prompt


def test_empty_facet_renders_empty_block_and_absent_note():
    empty = DnaFacet(
        key="economics",
        title="Business Economics",
        status=FacetStatus.UNKNOWN,
        provenance_tiers=[],
        items=[],
        note="economics",
    )
    assert render_economics_block(empty) == ""
    prompt = build_opportunity_user_prompt(
        **_kwargs(economics_block=render_economics_block(empty))
    )
    assert "no business economics captured" in prompt


# --------------------------------------------------------------------------- #
#  4 + 7. Low-confidence / unknown evidence is not presented as verified, and no
#         value is invented or upgraded.
# --------------------------------------------------------------------------- #


def test_insufficient_evidence_not_upgraded_to_verified():
    block = render_economics_block(_econ_facet())
    prompt = build_opportunity_user_prompt(**_kwargs(economics_block=block))
    # The unknown CAC keeps its honest tier — it is NOT relabelled USER_STATED/VERIFIED.
    assert "[UNKNOWN] Customer acquisition cost (CAC): INSUFFICIENT_EVIDENCE" in prompt
    assert "[VERIFIED] Customer acquisition cost" not in prompt
    assert "[USER_STATED] Customer acquisition cost" not in prompt


def test_system_prompt_carries_never_invent_discipline():
    sp = OPPORTUNITY_SYSTEM_PROMPT
    assert "Business economics (read-only)" in sp
    assert "NEVER invent" in sp
    assert "INSUFFICIENT_EVIDENCE metric stays unknown" in sp
    # Financial context alone must never fabricate an opportunity.
    assert "Financial context ALONE never justifies an opportunity" in sp


# --------------------------------------------------------------------------- #
#  6. Existing opportunity behaviour remains intact (additive, not a rewrite).
# --------------------------------------------------------------------------- #


def test_existing_sections_intact_with_economics_added():
    prompt = build_opportunity_user_prompt(
        **_kwargs(
            belief_block="- [channel] Reels beat static for leads (82%)",
            economics_block=render_economics_block(_econ_facet()),
        )
    )
    # Belief grounding (7.16) still present and unchanged.
    assert "LEARNED" in prompt
    assert "Reels beat static for leads" in prompt
    # Core structure untouched.
    assert "# Business" in prompt
    assert "# Your job" in prompt
    assert "OpportunityCenterReport" in prompt


# --------------------------------------------------------------------------- #
#  5 + 8. Brand isolation inherited from the accessor; read-only, no writes.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_resolver_renders_via_shared_renderer(monkeypatch):
    async def _fake_facet(session, *, tenant):
        return _econ_facet()

    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _fake_facet
    )
    out = await resolve_opportunity_economics(_SESSION, tenant=_tenant())
    # Parity with the single shared renderer — no bespoke opportunity formatting.
    assert out == render_economics_block(_econ_facet())
    assert "[USER_STATED] Unit price: 65.00 USD" in out


@pytest.mark.asyncio
async def test_resolver_forwards_exact_tenant_for_brand_isolation(monkeypatch):
    """The resolver passes the caller's TenantContext straight to the brand-scoped
    accessor — it never substitutes a brand, so isolation is inherited intact."""
    seen: dict = {}

    async def _capture(session, *, tenant):
        seen["tenant"] = tenant
        return _econ_facet()

    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _capture
    )
    t = _tenant()
    await resolve_opportunity_economics(_SESSION, tenant=t)
    assert seen["tenant"] is t
    assert seen["tenant"].brand_id == t.brand_id


@pytest.mark.asyncio
async def test_resolver_degrades_to_empty_on_failure(monkeypatch):
    async def _boom(session, *, tenant):
        raise RuntimeError("facet unavailable")

    monkeypatch.setattr(
        "aicmo.modules.business_dna.service.get_economics_facet", _boom
    )
    # The bare session stub exposes no DB methods: the resolver performs no writes
    # itself and never raises — a facet miss degrades to an empty block.
    out = await resolve_opportunity_economics(_SESSION, tenant=_tenant())
    assert out == ""


# --------------------------------------------------------------------------- #
#  Threading: _generate_narrative forwards economics_block into the prompt builder
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_generate_narrative_threads_economics_block(monkeypatch):
    captured: dict = {}

    def _fake_build(**kwargs):
        captured["economics_block"] = kwargs.get("economics_block")
        return "PROMPT"

    class _FakeRouter:
        async def generate(self, *a, **k):
            raise RuntimeError("no LLM in unit test")

    monkeypatch.setattr(center, "build_opportunity_user_prompt", _fake_build)
    monkeypatch.setattr(center, "get_llm_router", lambda: _FakeRouter())

    composed = {
        "counts_block": "(none)",
        "top_source_summary": None,
        "top_asset_summary": None,
        "trends_summary": None,
        "recent_content_summary": None,
        "recent_ads_summary": None,
        "signals": [],
    }
    # LLM raises → honest-failure fallback; we only assert the block was threaded in.
    narrative = await center._generate_narrative(
        profile=_profile(),
        composed=composed,
        memory_block=None,
        memory_rows=None,
        belief_block=None,
        economics_block="- [USER_STATED] Unit price: 65.00 USD",
    )
    assert captured["economics_block"] == "- [USER_STATED] Unit price: 65.00 USD"
    assert narrative is not None
