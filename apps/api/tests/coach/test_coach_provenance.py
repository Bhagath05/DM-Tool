"""Phase 7.18 — Coach evidence provenance.

Proves every evidence-grounded Coach recommendation is traceable to the actual
beliefs that supported it: the server attaches a structured ``EvidenceGrounding``
(validated beliefs + server-derived freshness-adjusted confidence + contradictory
findings) to each Coach response, honestly reports INSUFFICIENT_EVIDENCE when the
brand has no validated beliefs, degrades to no-provenance on failure, and never
leaks another brand's evidence. Provenance is server-derived — the LLM never
writes it.

Two layers:
  * Unit (no DB) — DTO attachment + serialization + API back-compat, and the
    defensive ("", None) degrade path.
  * Real-Postgres — resolve_coach_evidence grounds, surfaces multiple beliefs,
    marks stale evidence, reports contradictions, is honest on an empty brand,
    and is brand/tenant-isolated. Skips cleanly when no Postgres is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from aicmo.modules.belief.grounding import EvidenceGrounding, GroundedBelief
from aicmo.modules.coach.schemas import AnalyticsSummary, RealityCheck, WeeklyPlan


def _grounding(*, status: str = "grounded") -> EvidenceGrounding:
    return EvidenceGrounding(
        status=status,
        belief_count=1,
        beliefs=[
            GroundedBelief(
                category="channel", subject_key="channel:ig", statement="Reels beat static",
                confidence=72, evidence_count=3, status="active",
                freshness_reason="Current — evidence is fresh (≤30d old); confidence held at 72%.",
            )
        ],
        contradictions=[],
        note="Grounded in measured outcomes; confidence is server-derived.",
    )


# ---------------------------------------------------------------------
#  API back-compat: every Coach DTO validates WITHOUT provenance (default
#  None), so an older client / cached payload keeps working.
# ---------------------------------------------------------------------


def test_reality_check_back_compat_without_provenance():
    rc = RealityCheck.model_validate(
        {
            "feasibility_score": 50, "feasibility_label": "Aggressive but possible",
            "headline": "h", "realistic_milestones": [], "phased_growth_path": [],
            "risk_flags": [], "strategic_notes": [],
        }
    )
    assert rc.evidence_grounding is None


def test_weekly_plan_back_compat_without_provenance():
    wp = WeeklyPlan.model_validate(
        {"headline": "h", "week_focus": "f", "actions": [], "skip_this_week": [], "generated_at": "2026-01-01T00:00:00Z"}
    )
    assert wp.evidence_grounding is None


def test_analytics_summary_back_compat_without_provenance():
    s = AnalyticsSummary.model_validate(
        {
            "headline": "h", "what_to_do_next": "w", "overview_blurb": "o", "timeline_blurb": "t",
            "sources_blurb": "s", "landing_pages_blurb": "l", "top_assets_blurb": "a",
            "generated_at": "2026-01-01T00:00:00Z",
        }
    )
    assert s.evidence_grounding is None


# ---------------------------------------------------------------------
#  Provenance attaches + serializes with beliefs, confidence, freshness.
# ---------------------------------------------------------------------


def test_reality_check_serializes_provenance():
    rc = RealityCheck(
        feasibility_score=60, feasibility_label="Aggressive but possible", headline="h",
        realistic_milestones=[], phased_growth_path=[], risk_flags=[], strategic_notes=[],
        score_signals=[], evidence_grounding=_grounding(),
    )
    dumped = rc.model_dump(mode="json")
    assert dumped["evidence_grounding"]["status"] == "grounded"
    belief = dumped["evidence_grounding"]["beliefs"][0]
    assert belief["statement"] == "Reels beat static"
    assert belief["confidence"] == 72
    assert "fresh" in belief["freshness_reason"]


def test_insufficient_evidence_provenance_is_honest():
    g = EvidenceGrounding(
        status="insufficient_evidence", belief_count=0, beliefs=[], contradictions=[],
        note="No validated beliefs from past results yet — any recommendation here is a hypothesis.",
    )
    wp = WeeklyPlan(
        headline="h", week_focus="f", actions=[], skip_this_week=[],
        generated_at="2026-01-01T00:00:00Z", evidence_grounding=g,
    )
    assert wp.evidence_grounding is not None
    assert wp.evidence_grounding.status == "insufficient_evidence"
    assert wp.evidence_grounding.beliefs == []
    assert "hypothesis" in wp.evidence_grounding.note.lower()


# ---------------------------------------------------------------------
#  Defensive: a grounding failure degrades to ("", None) — never raises,
#  never fabricates provenance. (Malformed / missing provenance path.)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_coach_evidence_degrades_to_empty_and_none(monkeypatch):
    from aicmo.modules.coach import grounding as coach_grounding
    from aicmo.tenancy.context import TenantContext

    async def _boom(*_a, **_k):
        raise RuntimeError("belief store unavailable")

    monkeypatch.setattr(coach_grounding, "resolve_evidence_grounding", _boom)

    tenant = TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(), organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(), member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}), permissions=frozenset(),
    )

    block, grounding = await coach_grounding.resolve_coach_evidence(None, tenant=tenant)
    assert block == ""
    assert grounding is None
    # The 7.17 string contract still holds through the delegate.
    assert await coach_grounding.coach_belief_block(None, tenant=tenant) == ""


# ---------------------------------------------------------------------
#  Real-Postgres — grounded / multiple / stale / contradicted / insufficient
#  / brand + tenant isolation.
# ---------------------------------------------------------------------


def _tenant(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset(),
    )


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                       {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
    await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                       {"i": org, "s": f"o{tag}", "n": "O", "o": user})
    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})


async def _seed_belief(session, *, org, brand, statement, status="active", confidence=80, validated_at=None):
    from aicmo.modules.belief.models import Belief

    belief = Belief(
        id=uuid.uuid4(), organization_id=org, brand_id=brand,
        category="channel", subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement, scope={}, status=status,
        confidence=confidence, confidence_reason="measured outcomes",
        evidence_count=2, validated_at=validated_at or datetime.now(UTC),
    )
    session.add(belief)
    await session.flush()


@pytest.mark.asyncio
async def test_coach_evidence_provenance_real_postgres():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.coach.grounding import resolve_coach_evidence
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    empty = uuid.uuid4()
    fresh_stmt = "Reels beat static for leads"
    stale_stmt = "Email drove signups last year"
    b_stmt = "BRAND-B-ONLY must not leak"
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": empty, "o": org_a, "s": f"bz{ta}", "n": "Z", "u": user_a})
        async with AsyncSession(eng, expire_on_commit=False) as s:
            # Two ACTIVE beliefs (multiple supporting), one fresh + one stale (>180d).
            await _seed_belief(s, org=org_a, brand=brand_a, statement=fresh_stmt, confidence=82)
            await _seed_belief(
                s, org=org_a, brand=brand_a, statement=stale_stmt, confidence=80,
                validated_at=datetime.now(UTC) - timedelta(days=220),
            )
            await _seed_belief(s, org=org_a, brand=brand_a, statement="Discounts hurt margin", status="contradicted", confidence=28)
            await _seed_belief(s, org=org_b, brand=brand_b, statement=b_stmt, confidence=90)
            await s.commit()

        # Brand A — grounded, multiple supporting beliefs, stale marked, contradiction surfaced, isolated.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block, g = await resolve_coach_evidence(s, tenant=_tenant(org=org_a, brand=brand_a, user=user_a))
        assert g is not None
        assert g.status == "grounded"
        statements = {b.statement for b in g.beliefs}
        assert {fresh_stmt, stale_stmt} <= statements  # multiple supporting beliefs
        assert b_stmt not in statements  # cross-brand isolation
        # Stale belief carries a stale freshness reason + decayed (server-derived) confidence.
        stale = next(b for b in g.beliefs if b.statement == stale_stmt)
        assert stale.freshness_reason is not None and "stale" in stale.freshness_reason.lower()
        assert stale.confidence < 80
        # Contradiction represented accurately (do-not-rely).
        assert any("Discounts hurt margin" in c.statement for c in g.contradictions)
        assert b_stmt not in block

        # Empty brand (same org) — honest INSUFFICIENT_EVIDENCE, no fabricated beliefs.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            _blk, g2 = await resolve_coach_evidence(s, tenant=_tenant(org=org_a, brand=empty, user=user_a))
        assert g2 is not None and g2.status == "insufficient_evidence"
        assert g2.belief_count == 0 and g2.beliefs == []

        # Brand B (different org) — only its own belief; no cross-tenant leak.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            _blk, g3 = await resolve_coach_evidence(s, tenant=_tenant(org=org_b, brand=brand_b, user=user_b))
        assert g3 is not None
        assert {b.statement for b in g3.beliefs} == {b_stmt}
        assert fresh_stmt not in {b.statement for b in g3.beliefs}
    finally:
        async with eng.begin() as conn:
            for org_id, user_id in ((org_a, user_a), (org_b, user_b)):
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
        await eng.dispose()
