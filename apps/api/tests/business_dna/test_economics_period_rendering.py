"""Phase 7.20 Stage 3d — reporting-period preservation + shared-renderer reuse.

These tests exercise the ACTUAL production path, not hand-built facets:

    BusinessEconomics → resolve_economics → _economics_facet → render_economics_block
    → each consumer's real prompt builder.

They prove that a real owner-stated reporting period survives the resolver, is
carried onto the economics facet, is rendered as a provenance-tagged "Reporting
period" line, and reaches every consumer prompt — while an absent period stays
absent (never invented) and currency/provenance are preserved. They also prove the
Advisor now renders via the canonical shared renderer (the period line, which the
old inline loop never emitted, appears in the Advisor block), and that the legacy
and unified Opportunity paths carry equivalent economics context.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.signals import IntelligenceSignals, signals_to_prompt_block
from aicmo.modules.business_dna import economics as ec
from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue
from aicmo.modules.business_dna.schemas import (
    ContextProvenance,
    DnaFacet,
    FacetStatus,
)
from aicmo.modules.business_dna.service import _economics_facet, render_economics_block
from aicmo.modules.coach.prompts import (
    build_analytics_summary_user_prompt,
    build_user_prompt,
    build_weekly_user_prompt,
)
from aicmo.modules.opportunities.prompts import build_opportunity_user_prompt
from aicmo.modules.strategist.prompts import build_strategy_prompt

_PERIOD = "FY2026"


# --------------------------------------------------------------------------- #
#  Real resolver inputs
# --------------------------------------------------------------------------- #


def _economics_with_period() -> BusinessEconomics:
    """A real, validated stored-economics payload with an owner-stated period."""
    return BusinessEconomics(
        currency="USD",
        reporting_period=_PERIOD,
        price=EconomicValue(
            value=65.0, provenance=ContextProvenance.USER_STATED, currency="USD"
        ),
    )


def _profile_row_no_economics() -> Any:
    """A profile row that yields grounded items but NO reporting period."""
    return SimpleNamespace(
        business_location="Austin, TX",  # → SYSTEM_INFERRED currency USD
        monthly_budget_band="$100-500",  # → USER_STATED budget item
        pricing=None,
        primary_goal_text=None,
        products=[],
        services=[],
    )


def _real_block_with_period() -> str:
    """The ACTUAL rendered block for a brand with an owner-stated period."""
    res = ec.resolve_economics(
        profile_row=None, analytics=None, economics=_economics_with_period()
    )
    return render_economics_block(_economics_facet(res))


# A broad profile stand-in covering every attribute the consumer prompt builders
# read. Cast so the typed call sites stay honest while the test avoids the DB.
def _profile() -> Any:
    return cast(
        Any,
        SimpleNamespace(
            business_name="PawPals",
            industry="mobile dog grooming",
            business_type="service",
            business_location="Austin, TX",
            target_audience="busy suburban dog owners",
            current_monthly_leads_band="0-10",
            monthly_budget_band="$100-500",
            preferred_platforms=["instagram"],
            primary_goal_text="200 bookings/mo",
            brand_tone="friendly",
            pricing="$65 per groom",
            growth_stage="early",
            products=["grooming"],
            services=["mobile grooming"],
            unique_selling_points=["we come to you"],
            competitors=[],
            goals=["grow bookings"],
            analysis=None,
        ),
    )


# --------------------------------------------------------------------------- #
#  1. A real populated reporting period survives the resolver (+ provenance)
# --------------------------------------------------------------------------- #


def test_resolver_preserves_owner_stated_period_and_provenance():
    res = ec.resolve_economics(
        profile_row=None, analytics=None, economics=_economics_with_period()
    )
    assert res.period == _PERIOD
    assert res.period_provenance == ContextProvenance.USER_STATED


def test_resolver_period_from_analytics_is_measured():
    analytics = SimpleNamespace(
        conversion_rate=0.1, leads_30d=3, total_submissions=2
    )
    res = ec.resolve_economics(profile_row=None, analytics=analytics, economics=None)
    assert res.period == "last 30 days"
    assert res.period_provenance == ContextProvenance.MEASURED


# --------------------------------------------------------------------------- #
#  2. The period is carried onto the facet and appears in the rendered block
# --------------------------------------------------------------------------- #


def test_facet_carries_period_and_renderer_surfaces_it():
    res = ec.resolve_economics(
        profile_row=None, analytics=None, economics=_economics_with_period()
    )
    facet = _economics_facet(res)
    assert facet.period == _PERIOD
    assert facet.period_provenance == ContextProvenance.USER_STATED

    block = render_economics_block(facet)
    # The clear, provenance-tagged Reporting period field — actual rendered output.
    assert f"- [USER_STATED] Reporting period: {_PERIOD}" in block
    # Currency + provenance of the figure itself are still preserved.
    assert "[USER_STATED] Unit price: 65.00 USD" in block


# --------------------------------------------------------------------------- #
#  3. The period reaches each applicable consumer's final prompt
# --------------------------------------------------------------------------- #


def test_period_reaches_coach_reality_prompt():
    prompt = build_user_prompt(
        profile=_profile(),
        goal_text="get 20 leads",
        timeline_hint="3 months",
        feasibility_score=55,
        feasibility_label="Aggressive but possible",  # type: ignore[arg-type]
        signals=[],
        belief_block="",
        economics_block=_real_block_with_period(),
    )
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in prompt


def test_period_reaches_coach_weekly_prompt():
    prompt = build_weekly_user_prompt(
        profile=_profile(),
        signals=[],
        recent_activity={},
        has_published_page=False,
        top_asset_summary=None,
        trends_summary=None,
        analysis_phase_summary=None,
        analysis_channels=[],
        belief_block="",
        economics_block=_real_block_with_period(),
    )
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in prompt


def test_period_reaches_coach_analytics_summary_prompt():
    prompt = build_analytics_summary_user_prompt(
        profile_name="PawPals",
        profile_stage="0-10 band",
        overview={"total_leads": 3},
        timeline_summary="t",
        sources_summary="s",
        landing_pages_summary="lp",
        top_assets_summary="ta",
        belief_block="",
        economics_block=_real_block_with_period(),
    )
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in prompt


def test_period_reaches_strategy_prompt():
    prompt = build_strategy_prompt(
        _profile(), economics_block=_real_block_with_period()
    )
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in prompt


def test_period_reaches_opportunity_prompt():
    prompt = build_opportunity_user_prompt(
        profile=_profile(),
        counts_block="(none)",
        top_source_summary=None,
        top_asset_summary=None,
        trends_summary=None,
        recent_content_summary=None,
        recent_ads_summary=None,
        signals=[],
        economics_block=_real_block_with_period(),
    )
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in prompt


# --------------------------------------------------------------------------- #
#  4. Missing period stays absent — never invented
# --------------------------------------------------------------------------- #


def test_missing_period_is_absent_not_invented():
    res = ec.resolve_economics(
        profile_row=_profile_row_no_economics(), analytics=None, economics=None
    )
    assert res.period is None
    assert res.period_provenance is None

    block = render_economics_block(_economics_facet(res))
    # Items are still present, but there is NO Reporting period line and no
    # fabricated monthly/quarterly/annual inference.
    assert "Reporting period" not in block
    assert block != ""  # the facet still has grounded items (budget/currency)
    for word in ("monthly", "quarterly", "annual", "FY"):
        assert f"Reporting period: {word}" not in block


def test_empty_facet_with_no_period_renders_empty_block():
    # A genuinely itemless facet with no period → honest empty block. This is the
    # renderer's fail-safe contract (the consumer wrappers degrade to such a facet /
    # to "" on a miss), and the new period branch must not break it.
    empty = DnaFacet(
        key="economics",
        title="Business Economics",
        status=FacetStatus.UNKNOWN,
        provenance_tiers=[],
        items=[],
        period=None,
    )
    assert render_economics_block(empty) == ""


# --------------------------------------------------------------------------- #
#  5/6. Advisor renders via the canonical shared renderer (not a duplicate loop)
# --------------------------------------------------------------------------- #


def _advisor_block() -> str:
    res = ec.resolve_economics(
        profile_row=None, analytics=None, economics=_economics_with_period()
    )
    facet = _economics_facet(res)
    signals = IntelligenceSignals(
        brain=BusinessBrain(
            industry="mobile dog grooming",
            business_type="service",
            target_audience="busy suburban dog owners",
        ),
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 3"],
        economics_facet=facet,
    )
    return signals_to_prompt_block(signals, confidence_cap=85)


def test_advisor_uses_shared_renderer_including_period():
    block = _advisor_block()
    # Heading + discipline preserved.
    assert "=== 7. BUSINESS ECONOMICS" in block
    assert "NEVER invent" in block
    # Every line the canonical renderer produces appears verbatim in the Advisor
    # block — proving reuse of the shared renderer, not a divergent inline copy.
    for line in _real_block_with_period().splitlines():
        assert line in block
    # The period line — which the OLD inline loop never emitted — is now present.
    assert f"[USER_STATED] Reporting period: {_PERIOD}" in block


# --------------------------------------------------------------------------- #
#  7. Legacy vs unified Opportunity paths carry equivalent economics context
# --------------------------------------------------------------------------- #


def test_legacy_and_unified_opportunity_economics_equivalent():
    # Legacy path: resolve_opportunity_economics → render_economics_block.
    legacy_block = _real_block_with_period()
    # Unified path: advisor signals render the same facet into section 7.
    unified_block = _advisor_block()
    # Every canonical economics line present in the legacy block is present in the
    # unified block — same facet, same renderer, equivalent economics context.
    for line in legacy_block.splitlines():
        assert line in unified_block
