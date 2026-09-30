"""Phase 0 — the canonical context surfaces existing business/offer/channel
profile data (products, services, pricing, channels, goals) that was previously
dropped, only when the owner actually provided it. No fabrication; empty stays
empty; still read-only and tenant-scoped."""

from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.business_brain.schemas import (
    CompetitorResearchResponse,
    EvidenceListResponse,
    IcpListResponse,
    MarketResearchResponse,
)
from aicmo.modules.marketing_brain.service import build_context, context_to_prompt_block

_SVC = "aicmo.modules.marketing_brain.service"


def _tenant():
    return SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
    )


def _summary():
    return SimpleNamespace(
        known=["business_name"],
        unknown=["positioning"],
        limitations=[],
        evidence_counts={},
        latest_website_job=None,
        latest_competitor_job=None,
        latest_market_job=None,
    )


def _profile(**over):
    base = dict(
        business_name="Acme",
        website="https://acme.example",
        industry="SaaS",
        business_type="B2B",
        target_audience="Security teams",
        business_location="US",
        competitors=["Rival Inc"],
        monthly_budget_band="1k-5k",
        primary_goal_text="Get more leads",
        goals=["Get more leads", "Improve retention"],
        products=["Identity Cloud", "MFA Kit"],
        services=["Onboarding", "Managed SSO"],
        pricing="Starts at $99/mo",
        preferred_platforms=["instagram", "linkedin"],
    )
    base.update(over)
    return SimpleNamespace(**base)


@contextlib.contextmanager
def _patched(profile_row):
    """Patch every downstream read with empty/insufficient defaults, except the
    profile row under test."""
    empty_evidence = EvidenceListResponse(items=[], known_count=0, unknown_categories=[])
    empty_icps = IcpListResponse(items=[], status="INSUFFICIENT_EVIDENCE", message="none")
    empty_comp = CompetitorResearchResponse(status="INSUFFICIENT_EVIDENCE", message="none", candidates=[])
    empty_market = MarketResearchResponse(status="INSUFFICIENT_EVIDENCE", message="none", signals=[])
    overview = SimpleNamespace(
        total_leads=0, leads_7d=0, leads_30d=0, hot_leads=0, conversion_rate=0.0,
        landing_pages_published=0, total_views=0, total_submissions=0,
    )
    with (
        patch(f"{_SVC}.bb_service.get_context", new=AsyncMock(return_value=_summary())),
        patch(f"{_SVC}.bb_service.list_evidence", new=AsyncMock(return_value=empty_evidence)),
        patch(f"{_SVC}.bb_service.get_icp_hypotheses", new=AsyncMock(return_value=empty_icps)),
        patch(f"{_SVC}.bb_service.list_competitors", new=AsyncMock(return_value=empty_comp)),
        patch(f"{_SVC}.bb_service.list_market_signals", new=AsyncMock(return_value=empty_market)),
        patch(f"{_SVC}.onboarding_service.get_profile_or_none", new=AsyncMock(return_value=profile_row)),
        patch(f"{_SVC}.analytics_service.overview", new=AsyncMock(return_value=overview)),
        patch(f"{_SVC}.load_brand_memory", new=AsyncMock(return_value=[])),
        patch(
            f"{_SVC}.load_outcome_context",
            new=AsyncMock(return_value={"recent_outcomes": [], "failed_outcomes": [], "effectiveness_scores": []}),
        ),
        patch(f"{_SVC}.active_insights_for_module", new=AsyncMock(return_value=[])),
    ):
        yield


def _session():
    s = AsyncMock()
    s.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=0)))
    return s


@pytest.mark.asyncio
async def test_business_and_channel_data_surfaced_when_present():
    tenant = _tenant()
    with _patched(_profile()):
        ctx = await build_context(_session(), tenant=tenant)

    p = ctx.profile
    assert p.present is True
    # The exact profile values — nothing synthesized or reworded.
    assert p.products == ["Identity Cloud", "MFA Kit"]
    assert p.services == ["Onboarding", "Managed SSO"]
    assert p.pricing == "Starts at $99/mo"
    assert p.channels == ["instagram", "linkedin"]
    assert p.goals == ["Get more leads", "Improve retention"]

    block = context_to_prompt_block(ctx)
    assert "Identity Cloud" in block and "Managed SSO" in block
    assert "Starts at $99/mo" in block
    assert "instagram" in block


@pytest.mark.asyncio
async def test_absent_business_data_stays_empty_no_fabrication():
    tenant = _tenant()
    row = _profile(products=[], services=[], pricing=None, preferred_platforms=[], goals=[])
    with _patched(row):
        ctx = await build_context(_session(), tenant=tenant)

    p = ctx.profile
    assert p.present is True
    assert p.products == [] and p.services == [] and p.channels == [] and p.goals == []
    assert p.pricing is None

    block = context_to_prompt_block(ctx)
    # No fabricated lines when the data is absent.
    assert "Products:" not in block
    assert "Services:" not in block
    assert "Pricing:" not in block
    assert "Preferred channels:" not in block


@pytest.mark.asyncio
async def test_missing_profile_leaves_new_fields_empty():
    tenant = _tenant()
    with _patched(None):  # no business profile at all
        ctx = await build_context(_session(), tenant=tenant)

    p = ctx.profile
    assert p.present is False
    assert p.products == [] and p.services == [] and p.channels == [] and p.goals == []
    assert p.pricing is None
    block = context_to_prompt_block(ctx)
    assert "Profile: MISSING" in block


@pytest.mark.asyncio
async def test_context_build_issues_no_write_statements():
    """Read-only guarantee: the composer only ever runs read queries."""
    tenant = _tenant()
    session = _session()
    with _patched(_profile()):
        await build_context(session, tenant=tenant)
    for call in session.execute.await_args_list:
        stmt = repr(call).lower()
        assert not any(w in stmt for w in ("insert", "update", "delete"))
