"""Phase 7.20 Stage 3 — Business DNA economics integrated into the AI Advisor.

The advisor's unified signal gatherer loads the canonical economics facet
(read-only, facet-scoped) and the prompt builder renders it with an explicit
"never invent or upgrade a figure" discipline. Additive: existing sections and
grounding are untouched, and a facet read failure never aborts the advisor.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.signals import (
    IntelligenceSignals,
    gather_intelligence_signals,
    signals_to_prompt_block,
)
from aicmo.modules.business_dna.schemas import ContextProvenance, DnaFacet, DnaItem, FacetStatus
from aicmo.tenancy.context import TenantContext


def _brain() -> BusinessBrain:
    return BusinessBrain(
        industry="mobile dog grooming", business_type="service",
        target_audience="busy suburban dog owners who value convenience",
    )


def _signals(*, economics_facet: DnaFacet | None) -> IntelligenceSignals:
    return IntelligenceSignals(
        brain=_brain(), brain_complete=True, setup_steps=[], outcome_context={},
        connector_context={}, content_intelligence={}, lead_context={},
        analytics_signals=["Total leads: 3"], economics_facet=economics_facet,
    )


def _econ_facet() -> DnaFacet:
    return DnaFacet(
        key="economics", title="Business Economics", status=FacetStatus.POPULATED,
        provenance_tiers=[ContextProvenance.USER_STATED, ContextProvenance.SYSTEM_INFERRED],
        items=[
            DnaItem(label="Unit price", detail="100.00 USD", provenance=ContextProvenance.USER_STATED, source="economics"),
            DnaItem(label="Gross margin", detail="60.0%", provenance=ContextProvenance.SYSTEM_INFERRED, source="derived"),
            DnaItem(label="Customer acquisition cost (CAC)", detail="INSUFFICIENT_EVIDENCE — provide spend.", provenance=ContextProvenance.UNKNOWN, status="insufficient_evidence"),
        ],
        note="economics",
    )


def test_prompt_renders_economics_section_with_discipline():
    block = signals_to_prompt_block(_signals(economics_facet=_econ_facet()), confidence_cap=85)
    assert "=== 7. BUSINESS ECONOMICS" in block
    # The anti-fabrication discipline is explicit.
    assert "NEVER invent" in block and "INSUFFICIENT_EVIDENCE metric stays unknown" in block
    # Provenance-tagged lines are rendered with the values as-is (tier is the
    # canonical uppercase ContextProvenance value).
    assert "[USER_STATED] Unit price: 100.00 USD" in block
    assert "[SYSTEM_INFERRED] Gross margin: 60.0%" in block


def test_prompt_handles_absent_economics():
    block = signals_to_prompt_block(_signals(economics_facet=None), confidence_cap=85)
    assert "=== 7. BUSINESS ECONOMICS" in block
    assert "No business economics captured" in block
    # Existing sections remain intact (additive, not a rewrite).
    assert "=== 1. BUSINESS BRAIN (required) ===" in block
    assert "=== 6. INTERNAL ANALYTICS ===" in block


@pytest.mark.asyncio
async def test_gather_populates_economics_facet(monkeypatch):
    """gather_intelligence_signals loads the economics facet via the canonical
    accessor; a facet failure degrades to None without aborting the advisor."""

    async def _fake_facet(session, *, tenant):
        return _econ_facet()

    # Patch the canonical accessor (imported lazily inside gather) + the other
    # heavy loaders so this stays a focused unit test.
    monkeypatch.setattr("aicmo.modules.business_dna.service.get_economics_facet", _fake_facet)
    monkeypatch.setattr("aicmo.modules.marketing_brain.service.build_context", _raise)
    monkeypatch.setattr("aicmo.modules.belief.grounding.resolve_evidence_grounding", _raise)
    for name in ("load_outcome_context", "load_connector_context", "load_content_intelligence", "load_lead_context"):
        monkeypatch.setattr(f"aicmo.modules.advisor.signals.{name}", _async_dict)
    monkeypatch.setattr("aicmo.modules.analytics.service.overview", _fake_overview)
    monkeypatch.setattr("aicmo.modules.marketing_analytics.service.advisor_signal", _raise)

    tenant = _tenant()
    signals = await gather_intelligence_signals(object(), profile=_profile(), tenant=tenant)
    assert signals.economics_facet is not None
    assert signals.economics_facet.key == "economics"


# --- helpers for the gather unit test ---------------------------------------


async def _raise(*a, **k):
    raise RuntimeError("isolated: not under test")


async def _async_dict(*a, **k):
    return {}


async def _fake_overview(*a, **k):
    from types import SimpleNamespace

    return SimpleNamespace(total_leads=0, leads_7d=0, leads_30d=0, hot_leads=0, conversion_rate=0.0)


def _tenant() -> TenantContext:
    return TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(), organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(), member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view"}),
    )


def _profile():
    """Minimal profile stand-in — only the attributes load_business_brain reads
    (it accepts the response DTO or any attribute-compatible object)."""
    from types import SimpleNamespace

    return SimpleNamespace(
        industry="mobile dog grooming", business_type="service",
        target_audience="busy suburban dog owners who value convenience",
        monthly_budget_band="$100-500", primary_goal_text="200 bookings/mo",
        goals=["grow memberships"], business_location="Austin, TX",
        competitors=[], business_name="PawPals", preferred_platforms=["instagram"],
    )
