"""Phase 7.16 — shared evidence-grounding foundation (real Postgres).

Proves the one grounding helper every engine reuses: it grounds in ACTIVE beliefs
(validated findings), surfaces CONTRADICTED ones (contradictory evidence), is
honest (INSUFFICIENT_EVIDENCE with no active beliefs), and is brand-isolated.

Confidence/status come from the belief memory; this phase never asserts them.
Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


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


async def _seed_belief(session, *, org, brand, statement, status="active", confidence=80):
    from aicmo.modules.belief.models import Belief

    belief = Belief(
        id=uuid.uuid4(), organization_id=org, brand_id=brand,
        category="channel", subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement, scope={}, status=status,
        confidence=confidence, confidence_reason="measured outcomes",
        evidence_count=2, validated_at=datetime.now(UTC),
    )
    session.add(belief)
    await session.flush()


@pytest.mark.asyncio
async def test_grounding_active_contradicted_insufficient_and_isolation():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.belief.grounding import resolve_evidence_grounding
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    empty = uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": empty, "o": org_a, "s": f"bz{ta}", "n": "Z", "u": user_a})
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_belief(s, org=org_a, brand=brand_a, statement="Reels beat static for leads", status="active", confidence=82)
            await _seed_belief(s, org=org_a, brand=brand_a, statement="Email open rates were high", status="contradicted", confidence=30)
            await _seed_belief(s, org=org_b, brand=brand_b, statement="BRAND-B-ONLY must not leak", status="active", confidence=90)
            await s.commit()

        # Brand A: grounded in its ACTIVE belief; contradicted surfaced separately.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block, g = await resolve_evidence_grounding(s, tenant=_tenant(org=org_a, brand=brand_a, user=user_a))
        assert g.status == "grounded"
        assert [b.statement for b in g.beliefs] == ["Reels beat static for leads"]
        assert any("Email open rates" in c.statement for c in g.contradictions)
        assert "Reels beat static for leads" in block
        assert "CONTRADICTED" in block and "Email open rates" in block
        assert "BRAND-B-ONLY must not leak" not in block  # isolation

        # Empty brand → INSUFFICIENT_EVIDENCE, no fabrication.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            _blk, g2 = await resolve_evidence_grounding(s, tenant=_tenant(org=org_a, brand=empty, user=user_a))
        assert g2.status == "insufficient_evidence"
        assert g2.belief_count == 0 and g2.beliefs == []
        assert "hypothesis" in g2.note.lower()
    finally:
        async with eng.begin() as conn:
            for org_id, user_id in ((org_a, user_a), (org_b, user_b)):
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
        await eng.dispose()
