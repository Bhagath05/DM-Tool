"""Phase 7.20 Stage 1 — Business DNA against real Postgres.

Exercises the REAL belief machinery through the DNA read service: grounded +
contradicted beliefs, read-time freshness decay on a stale belief, strict
tenant/brand isolation, and the guarantee that composing the snapshot writes
nothing. Skips cleanly when no project Postgres is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from aicmo.modules.business_dna.schemas import ContextProvenance, FacetStatus


def _tenant(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view"}),
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


async def _seed_belief(session, *, org, brand, statement, status="active", confidence=80, validated_days_ago=1):
    from aicmo.modules.belief.models import Belief

    validated = datetime.now(UTC) - timedelta(days=validated_days_ago)
    belief = Belief(
        id=uuid.uuid4(), organization_id=org, brand_id=brand,
        category="channel", subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement, scope={}, status=status,
        confidence=confidence, confidence_reason="measured outcomes",
        evidence_count=2, validated_at=validated, valid_from=validated,
    )
    session.add(belief)
    await session.flush()


@pytest.mark.asyncio
async def test_dna_grounded_contradicted_stale_and_isolation_no_writes():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401  (register ORM models)
    from aicmo.modules.business_dna.service import get_business_dna
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    empty = uuid.uuid4()
    fresh_stmt = "Reels beat static for leads"
    stale_stmt = "Weekday posting won more reach"
    contra_stmt = "Email was our best channel"
    b_stmt = "BRAND-B-ONLY must not leak into brand A"
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": empty, "o": org_a, "s": f"bz{ta}", "n": "Z", "u": user_a})
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_belief(s, org=org_a, brand=brand_a, statement=fresh_stmt, status="active", confidence=82, validated_days_ago=1)
            await _seed_belief(s, org=org_a, brand=brand_a, statement=stale_stmt, status="active", confidence=80, validated_days_ago=240)
            await _seed_belief(s, org=org_a, brand=brand_a, statement=contra_stmt, status="contradicted", confidence=30, validated_days_ago=5)
            await _seed_belief(s, org=org_b, brand=brand_b, statement=b_stmt, status="active", confidence=90, validated_days_ago=1)
            await s.commit()

        # Count beliefs for brand A before/after → prove the read writes nothing.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            before = (await s.execute(text("SELECT count(*) FROM beliefs WHERE brand_id=:b"), {"b": brand_a})).scalar_one()
            dna_a = await get_business_dna(s, tenant=_tenant(org=org_a, brand=brand_a, user=user_a))
            assert not s.new and not s.dirty  # no pending writes queued by the read
            after = (await s.execute(text("SELECT count(*) FROM beliefs WHERE brand_id=:b"), {"b": brand_a})).scalar_one()
        assert before == after == 3

        beliefs = dna_a.facet("beliefs")
        assert beliefs is not None and beliefs.status == FacetStatus.POPULATED
        statements = {i.detail for i in beliefs.items}
        assert fresh_stmt in statements and stale_stmt in statements
        assert all(i.provenance == ContextProvenance.SYSTEM_INFERRED for i in beliefs.items)

        # Freshness decay: the 240-day belief (orig 80) is aged DOWN below 80 and
        # reads as stale; the 1-day belief holds at its stored confidence.
        fresh = next(i for i in beliefs.items if i.detail == fresh_stmt)
        stale = next(i for i in beliefs.items if i.detail == stale_stmt)
        assert fresh.confidence == 82
        assert stale.confidence is not None and stale.confidence < 80
        assert stale.freshness is not None and "stale" in stale.freshness.lower()

        # Contradiction surfaced, never silently dropped; brand B never leaks.
        assert any(contra_stmt in (c.detail or "") for c in beliefs.contradictions)
        assert b_stmt not in statements

        # Empty sibling brand (same org): honest INSUFFICIENT_EVIDENCE, no bleed.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            dna_empty = await get_business_dna(s, tenant=_tenant(org=org_a, brand=empty, user=user_a))
        beliefs_empty = dna_empty.facet("beliefs")
        assert beliefs_empty is not None and beliefs_empty.status == FacetStatus.INSUFFICIENT_EVIDENCE
        assert all(fresh_stmt != (i.detail or "") for i in beliefs_empty.items)

        # Brand B sees only its own belief (isolation the other direction).
        async with AsyncSession(eng, expire_on_commit=False) as s:
            dna_b = await get_business_dna(s, tenant=_tenant(org=org_b, brand=brand_b, user=user_b))
        beliefs_b = dna_b.facet("beliefs")
        assert beliefs_b is not None
        b_statements = {i.detail for i in beliefs_b.items}
        assert b_stmt in b_statements and fresh_stmt not in b_statements
    finally:
        async with eng.begin() as conn:
            for org_id, user_id in ((org_a, user_a), (org_b, user_b)):
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
        await eng.dispose()
