"""Phase 7.20 Stage 1 — canonical Business DNA read service (unit, no DB).

These tests stub the EXISTING composition services the DNA read service reuses
(Marketing Brain, belief grounding, the profile row, social audience patterns)
and assert the projection is correct, provenance-honest, deterministic, and
write-free. Postgres-backed isolation / contradiction / freshness tests live in
``test_business_dna_pg.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aicmo.modules.belief.grounding import EvidenceGrounding, GroundedBelief
from aicmo.modules.business_brain.schemas import (
    CompetitorCandidate,
    EvidenceItem,
    IcpItem,
    MarketSignal,
)
from aicmo.modules.business_dna import service as dna_service
from aicmo.modules.business_dna.schemas import ContextProvenance, FacetStatus
from aicmo.modules.marketing_brain.schemas import (
    MarketingBrainAnalyticsSnapshot,
    MarketingBrainContext,
    MarketingBrainLearningItem,
    MarketingBrainOutcomeItem,
    MarketingBrainProfileSnapshot,
    MarketingBrainRecommendationRef,
    MarketingBrainResearchSnapshot,
    MarketingBrainStrategySnapshot,
)
from aicmo.tenancy.context import TenantContext

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()


def _tenant(*, brand: uuid.UUID | None = _BRAND, permissions=frozenset({"analytics.view"})) -> TenantContext:
    return TenantContext(
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
        organization_id=_ORG,
        brand_id=brand,
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}),
        permissions=permissions,
    )


def _evidence(kind: str, category: str, claim: str, *, confidence: int) -> EvidenceItem:
    now = datetime.now(UTC)
    return EvidenceItem(
        id=uuid.uuid4(), kind=kind, category=category, claim=claim,  # type: ignore[arg-type]
        confidence=confidence, status="active", source_type="website",
        source_url="https://example.com", discovered_at=now, created_at=now,
    )


def _icp() -> IcpItem:
    return IcpItem(
        id=uuid.uuid4(), name="Busy suburban dog owners", description="Dual-income households valuing convenience",
        industries=["pet services"], company_size=None, geography=["US"], buyer_roles=["owner"],
        pain_points=["no time"], buying_signals=["searches mobile grooming"], exclusions=[],
        confidence=55, status="hypothesis", evidence_ids=[], created_at=datetime.now(UTC),
    )


def _full_mb() -> MarketingBrainContext:
    now = datetime.now(UTC)
    return MarketingBrainContext(
        brand_id=_BRAND, organization_id=_ORG, built_at=now,
        profile=MarketingBrainProfileSnapshot(
            present=True, business_name="PawPals", website="https://pawpals.example",
            industry="mobile dog grooming", business_type="service", target_audience="busy dog owners",
            location="Austin, TX", competitors=["SalonX"], monthly_budget_band="$100-500",
            primary_goal="200 bookings/mo", products=["Full groom"], services=["Bath"],
            pricing="$65 full groom", goals=["grow memberships"], channels=["instagram"],
            brand_voice="friendly",
        ),
        known=["business_name", "industry"], unknown=["evidence:market"],
        limitations=["Hypotheses are not confirmed facts."],
        facts=[_evidence("fact", "business", "Operates a mobile grooming van", confidence=80)],
        observations=[_evidence("observation", "audience", "Members rebook often", confidence=60)],
        hypotheses=[_evidence("hypothesis", "market", "Winter demand dips ~30%", confidence=45)],
        evidence_recommendations=[],
        evidence_counts={"fact": 1, "observation": 1, "hypothesis": 1, "recommendation": 0},
        superseded_excluded_count=2,
        icps=[_icp()], icp_status="ok", icp_message=None,
        research=MarketingBrainResearchSnapshot(
            competitor_candidates=[CompetitorCandidate(name="SalonX", reason="local salon chain", confidence=50, status="candidate")],
            competitor_status="ok",
            market_signals=[MarketSignal(signal_kind="demand", claim="rising search interest", evidence_kind="observation", confidence=55)],
            market_status="ok",
        ),
        analytics=MarketingBrainAnalyticsSnapshot(
            total_leads=12, leads_7d=3, leads_30d=9, hot_leads=2, conversion_rate=0.08,
            landing_pages_published=1, total_views=100, total_submissions=8,
        ),
        strategy=MarketingBrainStrategySnapshot(
            present=True, status="active", positioning="Convenience-first grooming",
            target_summary="Time-poor owners", recommendation="Push membership",
        ),
        recommendations=[MarketingBrainRecommendationRef(
            id=uuid.uuid4(), title="Launch membership promo", status="suggested", source_surface="advisor",
            confidence=70, impact_category="revenue", expected_result="+10 bookings", created_at=now, updated_at=now,
        )],
        outcomes=[MarketingBrainOutcomeItem(
            title="Ran reels campaign", delta_summary="+5 leads", effectiveness_score=72.0,
            source_surface="content", kind="evaluated_success",
        )],
        learning_insights=[MarketingBrainLearningItem(
            id=uuid.uuid4(), category="channel", observation="Reels outperform static", recommendation="Do more reels",
            expected_result="+engagement", confidence=65, direction="positive", status="active", learned_at=now,
        )],
    )


def _empty_mb() -> MarketingBrainContext:
    return MarketingBrainContext(
        brand_id=_BRAND, organization_id=_ORG, built_at=datetime.now(UTC),
        profile=MarketingBrainProfileSnapshot(present=False),
        known=[], unknown=["business_name", "industry"], limitations=[],
    )


def _grounding_full() -> EvidenceGrounding:
    return EvidenceGrounding(
        status="grounded", belief_count=1,
        beliefs=[GroundedBelief(
            category="channel", subject_key="channel:reels", statement="Reels beat static for leads",
            confidence=82, evidence_count=2, status="active", freshness_reason="Current — evidence is fresh.",
        )],
        contradictions=[GroundedBelief(
            category="channel", subject_key="channel:email", statement="Email was the best channel",
            confidence=30, evidence_count=1, status="contradicted", freshness_reason="aging",
        )],
        note="Grounded in measured outcomes.",
    )


def _grounding_empty() -> EvidenceGrounding:
    return EvidenceGrounding(
        status="insufficient_evidence", belief_count=0, beliefs=[], contradictions=[],
        note="No validated beliefs yet.",
    )


def _profile_row() -> SimpleNamespace:
    return SimpleNamespace(
        analysis={"business_summary": "A mobile grooming van business.", "audience_insights": ["Values convenience"]},
        brand_tone="friendly", brand_colors=["#0a0", "#fff"], fonts=["Inter"],
        keywords=["grooming", "mobile"], brand_rules=["Never over-promise"],
        writing_style="Warm and concise", unique_selling_points=["Comes to your home"],
    )


def _audience_pattern() -> SimpleNamespace:
    return SimpleNamespace(
        pattern_type="engagement_time", description="Engages most on weekday evenings",
        confidence_score=0.75, platform="instagram",
    )


def _patch(monkeypatch, *, mb, grounding, profile_row, patterns):
    async def _fake_build_context(session, *, tenant):
        return mb

    async def _fake_profile(session, brand_id):
        return profile_row

    async def _fake_grounding(session, *, tenant, **kw):
        return ("block", grounding)

    async def _fake_patterns(session, *, brand_id, platform=None):
        return list(patterns)

    monkeypatch.setattr("aicmo.modules.marketing_brain.service.build_context", _fake_build_context)
    monkeypatch.setattr("aicmo.modules.onboarding.service.get_profile_or_none", _fake_profile)
    monkeypatch.setattr("aicmo.modules.belief.grounding.resolve_evidence_grounding", _fake_grounding)
    monkeypatch.setattr("aicmo.modules.social.service.list_audience_patterns", _fake_patterns)


# ---------------------------------------------------------------------
#  Complete DNA
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_dna_has_all_ten_facets_populated(monkeypatch):
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())

    keys = [f.key for f in dna.facets]
    assert keys == list(dna_service._FACET_ORDER)  # deterministic canonical order

    by = {f.key: f for f in dna.facets}
    for k in ("identity", "brand_identity", "offer_positioning", "audience", "market", "evidence", "beliefs", "performance", "learning"):
        assert by[k].status == FacetStatus.POPULATED, k
    assert by["economics"].status == FacetStatus.UNKNOWN
    assert dna.brand_id == _BRAND and dna.organization_id == _ORG


@pytest.mark.asyncio
async def test_provenance_tiers_are_correct_per_facet(monkeypatch):
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    by = {f.key: f for f in dna.facets}

    # Identity + brand identity are owner-stated (plus one SYSTEM_INFERRED AI summary in identity).
    assert ContextProvenance.USER_STATED in by["identity"].provenance_tiers
    assert all(i.provenance == ContextProvenance.USER_STATED for i in by["brand_identity"].items)
    # Evidence: a FACT is VERIFIED; observations/hypotheses are SYSTEM_INFERRED.
    ev_tiers = {i.provenance for i in by["evidence"].items}
    assert ContextProvenance.VERIFIED in ev_tiers
    assert ContextProvenance.SYSTEM_INFERRED in ev_tiers
    # Beliefs are SYSTEM_INFERRED conclusions (never VERIFIED).
    assert all(i.provenance == ContextProvenance.SYSTEM_INFERRED for i in by["beliefs"].items)
    # Performance is MEASURED.
    assert all(i.provenance == ContextProvenance.MEASURED for i in by["performance"].items)
    # Audience carries both a SYSTEM_INFERRED ICP and a MEASURED social pattern.
    aud_tiers = {i.provenance for i in by["audience"].items}
    assert {ContextProvenance.SYSTEM_INFERRED, ContextProvenance.MEASURED} <= aud_tiers


@pytest.mark.asyncio
async def test_confidence_never_llm_asserted(monkeypatch):
    """USER_STATED items never carry a confidence number (there is nothing to
    derive it from); beliefs/evidence confidence is server-derived and present."""
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    for f in dna.facets:
        for item in f.items:
            if item.provenance == ContextProvenance.USER_STATED:
                assert item.confidence is None, f"{f.key}:{item.label}"
    beliefs = dna.facet("beliefs")
    assert beliefs is not None and beliefs.items[0].confidence == 82
    assert beliefs.items[0].freshness is not None  # freshness is server-derived


@pytest.mark.asyncio
async def test_beliefs_surface_contradictions(monkeypatch):
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    beliefs = dna.facet("beliefs")
    assert beliefs is not None
    assert len(beliefs.contradictions) == 1
    assert "Email was the best channel" in beliefs.contradictions[0].detail


# ---------------------------------------------------------------------
#  Partial / missing
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_dna_marks_empty_facets_insufficient_or_unknown(monkeypatch):
    _patch(monkeypatch, mb=_empty_mb(), grounding=_grounding_empty(), profile_row=None, patterns=[])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    by = {f.key: f for f in dna.facets}
    # No profile → identity UNKNOWN (source itself absent).
    assert by["identity"].status == FacetStatus.UNKNOWN
    assert by["brand_identity"].status == FacetStatus.UNKNOWN
    # Beliefs source exists but is empty → INSUFFICIENT_EVIDENCE (honest, not UNKNOWN).
    assert by["beliefs"].status == FacetStatus.INSUFFICIENT_EVIDENCE
    assert by["economics"].status == FacetStatus.UNKNOWN


@pytest.mark.asyncio
async def test_economics_is_always_deferred_unknown(monkeypatch):
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    econ = dna.facet("economics")
    assert econ is not None
    assert econ.status == FacetStatus.UNKNOWN
    assert econ.items == []
    assert econ.provenance_tiers == [ContextProvenance.UNKNOWN]
    assert "Stage 2" in (econ.note or "")


@pytest.mark.asyncio
async def test_provenance_legend_present_and_canonical(monkeypatch):
    _patch(monkeypatch, mb=_empty_mb(), grounding=_grounding_empty(), profile_row=None, patterns=[])
    dna = await dna_service.get_business_dna(object(), tenant=_tenant())
    assert set(dna.provenance_legend.keys()) == {t.value for t in ContextProvenance}


# ---------------------------------------------------------------------
#  Determinism + brand requirement + no writes
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_output_apart_from_timestamp(monkeypatch):
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    tenant = _tenant()
    a = await dna_service.get_business_dna(object(), tenant=tenant)
    b = await dna_service.get_business_dna(object(), tenant=tenant)
    da = a.model_dump(mode="json"); da.pop("generated_at")
    db = b.model_dump(mode="json"); db.pop("generated_at")
    assert da == db


@pytest.mark.asyncio
async def test_requires_brand(monkeypatch):
    from fastapi import HTTPException

    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[])
    with pytest.raises(HTTPException) as ei:
        await dna_service.get_business_dna(object(), tenant=_tenant(brand=None))
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_service_issues_no_writes(monkeypatch):
    """The read service must never add/flush/commit/delete. All composed reads are
    stubbed, so a write guard proves the service body itself is write-free."""
    _patch(monkeypatch, mb=_full_mb(), grounding=_grounding_full(), profile_row=_profile_row(), patterns=[_audience_pattern()])
    guard = MagicMock(name="session")
    for m in ("add", "add_all", "delete", "flush", "commit", "merge", "execute", "scalar", "scalars"):
        getattr(guard, m).side_effect = AssertionError(f"session.{m} must not be called")
    dna = await dna_service.get_business_dna(guard, tenant=_tenant())
    assert dna.facet("identity") is not None  # completed without touching the session


# ---------------------------------------------------------------------
#  Permission enforcement (the read endpoint is gated by analytics.view)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_requires_analytics_view_permission():
    from aicmo.modules.business_dna.router import _RequireRead
    from aicmo.tenancy.exceptions import NotAuthorized

    allowed = _tenant(permissions=frozenset({"analytics.view"}))
    assert await _RequireRead(tenant=allowed) is allowed  # passes through

    denied = _tenant(permissions=frozenset({"content.create"}))
    with pytest.raises(NotAuthorized):
        await _RequireRead(tenant=denied)
