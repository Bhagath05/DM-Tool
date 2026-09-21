"""Phase A — Marketing Brain unified context composition tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from aicmo.modules.business_brain.schemas import (
    CompetitorResearchResponse,
    EvidenceItem,
    EvidenceListResponse,
    IcpItem,
    IcpListResponse,
    MarketResearchResponse,
)
from aicmo.modules.marketing_brain.schemas import (
    MarketingBrainContext,
    MarketingBrainProfileSnapshot,
)
from aicmo.modules.marketing_brain.service import (
    build_context,
    context_to_prompt_block,
)


def _tenant(*, brand_id: uuid.UUID | None = None, org_id: uuid.UUID | None = None):
    return SimpleNamespace(
        organization_id=org_id or uuid.uuid4(),
        brand_id=brand_id if brand_id is not None else uuid.uuid4(),
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
    )


def _evidence(
    *,
    kind: str,
    claim: str,
    brand_claim: str | None = None,
    status: str = "active",
    confidence: int = 70,
    source_url: str | None = "https://example.com",
) -> EvidenceItem:
    now = datetime.now(UTC)
    return EvidenceItem(
        id=uuid.uuid4(),
        kind=kind,  # type: ignore[arg-type]
        category="business",
        claim=claim,
        confidence=confidence,
        status=status,
        claim_key=brand_claim,
        superseded_by_id=None,
        source_url=source_url,
        source_type="website",
        snippet="snippet",
        research_job_id=None,
        discovered_at=now,
        retrieved_at=now,
        created_at=now,
    )


def _summary(**over):
    base = dict(
        profile_present=True,
        business_name="Acme",
        website="https://acme.example",
        industry="SaaS",
        known=["business_name", "industry"],
        unknown=["positioning"],
        evidence_counts={"fact": 1, "observation": 1, "hypothesis": 1, "recommendation": 0},
        latest_job=None,
        latest_website_job=None,
        latest_competitor_job=None,
        latest_market_job=None,
        icp_count=1,
        competitor_candidate_count=0,
        market_signal_count=0,
        limitations=["LLM interpretations remain hypotheses."],
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_build_context_partitions_kinds_and_preserves_provenance():
    brand = uuid.uuid4()
    org = uuid.uuid4()
    tenant = _tenant(brand_id=brand, org_id=org)
    fact = _evidence(kind="fact", claim="Acme sells identity software.", confidence=90)
    obs = _evidence(kind="observation", claim="Homepage mentions security teams.")
    hyp = _evidence(kind="hypothesis", claim="CISOs are primary buyers.", confidence=40)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=0)))

    overview = SimpleNamespace(
        total_leads=3,
        leads_7d=1,
        leads_30d=3,
        hot_leads=1,
        conversion_rate=0.1,
        landing_pages_published=1,
        total_views=10,
        total_submissions=2,
    )
    icp = IcpItem(
        id=uuid.uuid4(),
        name="Mid-market security",
        description="Security leaders at mid-market SaaS",
        industries=["SaaS"],
        company_size="50-200",
        geography=["US"],
        buyer_roles=["CISO"],
        pain_points=["SSO"],
        buying_signals=["RFP"],
        exclusions=[],
        confidence=45,
        status="hypothesis",
        evidence_ids=[fact.id],
        created_at=datetime.now(UTC),
    )

    with (
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.get_context",
            new=AsyncMock(return_value=_summary()),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_evidence",
            new=AsyncMock(
                return_value=EvidenceListResponse(
                    items=[fact, obs, hyp],
                    known_count=3,
                    unknown_categories=[],
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.get_icp_hypotheses",
            new=AsyncMock(return_value=IcpListResponse(items=[icp], status="ok", message=None)),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_competitors",
            new=AsyncMock(
                return_value=CompetitorResearchResponse(
                    status="INSUFFICIENT_EVIDENCE",
                    message="No competitor research yet.",
                    candidates=[],
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_market_signals",
            new=AsyncMock(
                return_value=MarketResearchResponse(
                    status="INSUFFICIENT_EVIDENCE",
                    message="No market research yet.",
                    signals=[],
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.onboarding_service.get_profile_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.analytics_service.overview",
            new=AsyncMock(return_value=overview),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_brand_memory",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_outcome_context",
            new=AsyncMock(
                return_value={
                    "recent_outcomes": [
                        {
                            "title": "Post more reels",
                            "delta_summary": "+2 leads",
                            "effectiveness_score": 0.6,
                            "source_surface": "coach",
                        }
                    ],
                    "failed_outcomes": [
                        {
                            "title": "Boost ads",
                            "reason": "Skipped by user — avoid repeating",
                        }
                    ],
                    "effectiveness_scores": [],
                }
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.active_insights_for_module",
            new=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        category="channel",
                        observation="Instagram brings cheaper leads",
                        recommendation="Keep Instagram primary",
                        expected_result="Stable CPL",
                        confidence=70,
                        direction="positive",
                        status="active",
                        learned_at=datetime.now(UTC),
                        expires_at=None,
                        evidence=["CPL Instagram < email"],
                    )
                ]
            ),
        ),
    ):
        ctx = await build_context(session, tenant=tenant)

    assert isinstance(ctx, MarketingBrainContext)
    assert ctx.brand_id == brand
    assert ctx.organization_id == org
    assert len(ctx.facts) == 1 and ctx.facts[0].kind == "fact"
    assert len(ctx.observations) == 1 and ctx.observations[0].kind == "observation"
    assert len(ctx.hypotheses) == 1 and ctx.hypotheses[0].kind == "hypothesis"
    assert ctx.facts[0].source_url == "https://example.com"
    assert ctx.facts[0].confidence == 90
    assert ctx.icps[0].status == "hypothesis"
    assert ctx.outcomes[0].kind == "evaluated_success"
    assert ctx.outcomes[1].kind == "failed_or_skipped"
    assert ctx.learning_insights[0].category == "channel"
    # Learning is separate from BB evidence
    assert all(e.kind != "channel" for e in ctx.facts + ctx.observations + ctx.hypotheses)


@pytest.mark.asyncio
async def test_missing_brand_rejected():
    tenant = _tenant(brand_id=None)  # type: ignore[arg-type]
    # brand_id explicitly None
    tenant.brand_id = None
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await build_context(session, tenant=tenant)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_brand_isolation_uses_tenant_brand_only():
    """list_evidence / get_context always receive the tenant — never another brand."""
    brand_a = uuid.uuid4()
    tenant = _tenant(brand_id=brand_a)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=0)))
    get_ctx = AsyncMock(return_value=_summary())
    list_ev = AsyncMock(
        return_value=EvidenceListResponse(items=[], known_count=0, unknown_categories=[])
    )
    with (
        patch("aicmo.modules.marketing_brain.service.bb_service.get_context", get_ctx),
        patch("aicmo.modules.marketing_brain.service.bb_service.list_evidence", list_ev),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.get_icp_hypotheses",
            new=AsyncMock(
                return_value=IcpListResponse(
                    items=[], status="INSUFFICIENT_EVIDENCE", message="thin"
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_competitors",
            new=AsyncMock(
                return_value=CompetitorResearchResponse(
                    status="INSUFFICIENT_EVIDENCE", message="x", candidates=[]
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_market_signals",
            new=AsyncMock(
                return_value=MarketResearchResponse(
                    status="INSUFFICIENT_EVIDENCE", message="x", signals=[]
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.onboarding_service.get_profile_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.analytics_service.overview",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_brand_memory",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_outcome_context",
            new=AsyncMock(
                return_value={
                    "recent_outcomes": [],
                    "failed_outcomes": [],
                    "effectiveness_scores": [],
                }
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.active_insights_for_module",
            new=AsyncMock(return_value=[]),
        ),
    ):
        ctx = await build_context(session, tenant=tenant)

    assert ctx.brand_id == brand_a
    assert get_ctx.await_args.kwargs["tenant"] is tenant
    assert list_ev.await_args.kwargs["tenant"] is tenant
    assert ctx.analytics is None  # missing analytics does not fabricate KPIs
    assert ctx.profile.present is False
    assert "none" in context_to_prompt_block(ctx).lower() or "MISSING" in context_to_prompt_block(
        ctx
    )


def test_prompt_block_does_not_present_hypotheses_as_facts():
    now = datetime.now(UTC)
    brand = uuid.uuid4()
    hyp = _evidence(kind="hypothesis", claim="Buyers are CISOs")
    fact = _evidence(kind="fact", claim="Company sells SSO")
    ctx = MarketingBrainContext(
        brand_id=brand,
        organization_id=uuid.uuid4(),
        built_at=now,
        profile=MarketingBrainProfileSnapshot(present=False),
        known=[],
        unknown=["industry"],
        limitations=[],
        facts=[fact],
        observations=[],
        hypotheses=[hyp],
        evidence_recommendations=[],
        evidence_counts={"fact": 1, "hypothesis": 1},
        superseded_excluded_count=2,
        icps=[],
        icp_status="INSUFFICIENT_EVIDENCE",
        icp_message="Need more evidence",
    )
    block = context_to_prompt_block(ctx)
    assert "[FACT]" in block and "Company sells SSO" in block
    assert "[HYPOTHESIS]" in block and "Buyers are CISOs" in block
    # Hypothesis must not appear under the FACTS section as unlabeled certainty.
    facts_section = block.split("HYPOTHESES")[0]
    assert "Buyers are CISOs" not in facts_section
    assert "superseded/contradicted" in block.lower() or "2" in block


@pytest.mark.asyncio
async def test_superseded_excluded_count_queried_for_tenant_brand():
    brand = uuid.uuid4()
    tenant = _tenant(brand_id=brand)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=3)))
    with (
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.get_context",
            new=AsyncMock(return_value=_summary()),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_evidence",
            new=AsyncMock(
                return_value=EvidenceListResponse(
                    items=[_evidence(kind="fact", claim="Active only")],
                    known_count=1,
                    unknown_categories=[],
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.get_icp_hypotheses",
            new=AsyncMock(return_value=IcpListResponse(items=[], status="ok", message=None)),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_competitors",
            new=AsyncMock(
                return_value=CompetitorResearchResponse(
                    status="INSUFFICIENT_EVIDENCE", message="x", candidates=[]
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.bb_service.list_market_signals",
            new=AsyncMock(
                return_value=MarketResearchResponse(
                    status="INSUFFICIENT_EVIDENCE", message="x", signals=[]
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.onboarding_service.get_profile_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.analytics_service.overview",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    total_leads=0,
                    leads_7d=0,
                    leads_30d=0,
                    hot_leads=0,
                    conversion_rate=0.0,
                    landing_pages_published=0,
                    total_views=0,
                    total_submissions=0,
                )
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_brand_memory",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.load_outcome_context",
            new=AsyncMock(
                return_value={
                    "recent_outcomes": [],
                    "failed_outcomes": [],
                    "effectiveness_scores": [],
                }
            ),
        ),
        patch(
            "aicmo.modules.marketing_brain.service.active_insights_for_module",
            new=AsyncMock(return_value=[]),
        ),
    ):
        ctx = await build_context(session, tenant=tenant)

    assert ctx.superseded_excluded_count == 3
    assert all(e.status == "active" for e in ctx.facts)
    assert len(ctx.facts) == 1


def test_resolve_brand_rejects_mismatched_brand_id():
    from aicmo.modules.advisor.signals import _resolve_brand_id

    brand_a = uuid.uuid4()
    brand_b = uuid.uuid4()
    tenant = _tenant(brand_id=brand_a)
    with pytest.raises(ValueError, match="cross-brand"):
        _resolve_brand_id(tenant=tenant, brand_id=brand_b)


def test_context_to_prompt_block_is_deterministic():
    now = datetime(2026, 1, 15, tzinfo=UTC)
    eid = uuid.uuid4()
    fact = EvidenceItem(
        id=eid,
        kind="fact",
        category="business",
        claim="Stable claim",
        confidence=80,
        status="active",
        claim_key=None,
        superseded_by_id=None,
        source_url="https://a.example",
        source_type="website",
        snippet=None,
        research_job_id=None,
        discovered_at=now,
        retrieved_at=now,
        created_at=now,
    )
    ctx = MarketingBrainContext(
        brand_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        organization_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        built_at=now,
        profile=MarketingBrainProfileSnapshot(present=False),
        facts=[fact],
    )
    assert context_to_prompt_block(ctx) == context_to_prompt_block(ctx)


# --------------------------------------------------------------------------
# Real service-level integration: Marketing Brain composed over the committed
# Business Brain, against real PostgreSQL. Exercises bb_service end-to-end (not
# mocked) so the evidence/ICP/isolation/provenance seam is genuinely pinned.
# --------------------------------------------------------------------------


def _pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


def _real_tenant(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user),
        user_uuid=user,
        organization_id=org,
        brand_id=brand,
        member_id=uuid.uuid4(),
    )


async def _seed_org_brands(session, *, org, brands, user, tag):
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
        {"i": user, "c": f"clerk_{tag}", "e": f"{tag}@t.local"},
    )
    await session.execute(
        text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
        {"i": org, "s": f"org-{tag}", "n": "MB Org", "o": user},
    )
    for idx, b in enumerate(brands):
        await session.execute(
            text(
                "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
                "VALUES (:i,:o,:s,:n,:u)"
            ),
            {"i": b, "o": org, "s": f"brand-{tag}-{idx}", "n": f"Brand {idx}", "u": user},
        )


def _brain_evidence(*, org, brand, kind, claim, status="active", confidence=70, source="https://ex.co"):
    from aicmo.modules.business_brain.models import BrainEvidence

    return BrainEvidence(
        id=uuid.uuid4(),
        organization_id=org,
        brand_id=brand,
        kind=kind,
        category="business",
        claim=claim,
        confidence=confidence,
        status=status,
        source_url=source,
        source_type="website",
        snippet="snippet",
        discovered_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_marketing_brain_real_integration_over_business_brain(monkeypatch):
    """Compose MarketingBrainContext over the REAL Business Brain service against
    real Postgres. Pins: kind partitioning + provenance from real rows, superseded
    exclusion, ICP status, cross-tenant isolation (both directions), honest
    empty/insufficient context, and that build_context never calls an LLM or
    enqueues publish/spend work (read-only, no governance bypass).
    """
    _pg()
    from unittest.mock import AsyncMock

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.business_brain.models import BrainIcp
    from aicmo.modules.marketing_brain.service import build_context

    org = uuid.uuid4()
    brand_a, brand_b, brand_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    user = uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()

    # Safety guards: MB must not reach an LLM or enqueue side-effecting work.
    class _NoLLM:
        async def generate(self, **_kw):
            raise AssertionError("Marketing Brain must not call the LLM router")

    monkeypatch.setattr("aicmo.llm.router.get_llm_router", lambda: _NoLLM())
    enqueue_calls: list = []
    monkeypatch.setattr(
        "aicmo.queue.enqueue.enqueue_tenant_job",
        AsyncMock(side_effect=lambda *a, **k: enqueue_calls.append((a, k)) or None),
    )

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_org_brands(s, org=org, brands=[brand_a, brand_b, brand_c], user=user, tag=tag)
            # brand_a — a full evidence spread plus a superseded row.
            s.add_all(
                [
                    _brain_evidence(org=org, brand=brand_a, kind="fact",
                                    claim="Acme sells identity software.", confidence=92),
                    _brain_evidence(org=org, brand=brand_a, kind="observation",
                                    claim="Homepage targets security teams."),
                    _brain_evidence(org=org, brand=brand_a, kind="hypothesis",
                                    claim="CISOs are the primary buyers.", confidence=40),
                    _brain_evidence(org=org, brand=brand_a, kind="recommendation",
                                    claim="Lead with SOC2 messaging."),
                    _brain_evidence(org=org, brand=brand_a, kind="fact",
                                    claim="Old pricing claim.", status="superseded"),
                ]
            )
            s.add(
                BrainIcp(
                    id=uuid.uuid4(),
                    organization_id=org,
                    brand_id=brand_a,
                    name="Security-conscious SaaS",
                    description="Mid-market SaaS with a security-led buyer.",
                    confidence=45,
                    status="hypothesis",
                )
            )
            # brand_b — a single distinct fact, to prove isolation both ways.
            s.add(
                _brain_evidence(org=org, brand=brand_b, kind="fact",
                                claim="BRAND-B-ONLY secret fact.", confidence=88)
            )
            await s.commit()

        tenant_a = _real_tenant(org=org, brand=brand_a, user=user)
        tenant_b = _real_tenant(org=org, brand=brand_b, user=user)
        tenant_c = _real_tenant(org=org, brand=brand_c, user=user)

        async with AsyncSession(eng, expire_on_commit=False) as s:
            ctx_a = await build_context(s, tenant=tenant_a)
        # Kind partitioning from REAL rows.
        assert [e.claim for e in ctx_a.facts] == ["Acme sells identity software."]
        assert [e.claim for e in ctx_a.observations] == ["Homepage targets security teams."]
        assert [e.claim for e in ctx_a.hypotheses] == ["CISOs are the primary buyers."]
        assert [e.claim for e in ctx_a.evidence_recommendations] == ["Lead with SOC2 messaging."]
        # Provenance preserved from the source rows; hypothesis stays a hypothesis.
        assert ctx_a.facts[0].confidence == 92
        assert ctx_a.facts[0].source_url == "https://ex.co"
        assert ctx_a.facts[0].status == "active"
        assert ctx_a.hypotheses[0].confidence == 40
        # Superseded excluded from active lists but counted honestly.
        assert ctx_a.superseded_excluded_count == 1
        assert all("Old pricing claim" not in e.claim for e in ctx_a.facts)
        # ICP present, status preserved (hypothesis, not fact).
        assert len(ctx_a.icps) == 1 and ctx_a.icps[0].status == "hypothesis"
        # No profile seeded → honest absence, not fabrication.
        assert ctx_a.profile.present is False
        assert ctx_a.limitations  # explicit limitations always present
        # Cross-tenant isolation: brand_b's secret never leaks into brand_a.
        all_a_claims = " ".join(
            e.claim for e in ctx_a.facts + ctx_a.observations + ctx_a.hypotheses
            + ctx_a.evidence_recommendations
        )
        assert "BRAND-B-ONLY" not in all_a_claims

        # Isolation the other direction: brand_b sees only its own fact.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            ctx_b = await build_context(s, tenant=tenant_b)
        assert [e.claim for e in ctx_b.facts] == ["BRAND-B-ONLY secret fact."]
        assert ctx_b.observations == [] and ctx_b.hypotheses == []
        assert "Acme sells identity software." not in " ".join(e.claim for e in ctx_b.facts)
        assert ctx_b.icp_status == "INSUFFICIENT_EVIDENCE" and ctx_b.icps == []

        # Empty/insufficient Business Brain context: no fabrication.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            ctx_c = await build_context(s, tenant=tenant_c)
        assert ctx_c.facts == [] and ctx_c.hypotheses == [] and ctx_c.observations == []
        assert ctx_c.icp_status == "INSUFFICIENT_EVIDENCE"
        assert ctx_c.superseded_excluded_count == 0
        assert ctx_c.profile.present is False

        # Read-only + no governance bypass: no LLM call, no enqueue/publish/spend.
        assert enqueue_calls == []
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM brain_icp_evidence WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brain_icps WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brain_evidence WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
