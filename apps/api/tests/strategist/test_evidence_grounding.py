"""Phase 7.15 — evidence-grounded strategy (real Postgres).

Proves the learn -> strategize loop closure the unit tests can't:
  * resolve_strategy_evidence grounds in the brand's ACTIVE evidence-graded
    beliefs (status "grounded", correct count + confidence);
  * a brand with no validated beliefs yields INSUFFICIENT_EVIDENCE (no
    fabrication);
  * cross-brand isolation — one brand's beliefs never ground another's strategy;
  * run_strategy persists the provenance on the strategy record (success path).

Confidence/status come from the belief memory; this phase never asserts them.
Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    await _insert_brand(conn, org=org, brand=brand, user=user, tag=tag)


async def _insert_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})


async def _seed_active_belief(session, *, org, brand, statement, confidence=80):
    from aicmo.modules.belief.models import Belief

    belief = Belief(
        id=uuid.uuid4(), organization_id=org, brand_id=brand,
        category="channel", subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement, scope={}, status="active",
        confidence=confidence, confidence_reason="2 supporting measured outcomes",
        evidence_count=2, validated_at=datetime.now(UTC),
    )
    session.add(belief)
    await session.flush()
    return belief.id


@pytest.mark.asyncio
async def test_grounding_uses_active_beliefs_and_isolates_by_brand():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — register the ORM graph
    from aicmo.modules.strategist.grounding import resolve_strategy_evidence
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    empty_c = uuid.uuid4()  # a brand under org_a with no beliefs
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
            await _insert_brand(conn, org=org_a, brand=empty_c, user=user_a, tag=f"{ta}c")

        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_active_belief(s, org=org_a, brand=brand_a, statement="Reels beat static for leads", confidence=82)
            await _seed_active_belief(s, org=org_a, brand=brand_a, statement="Tuesday posts get more saves", confidence=66)
            await _seed_active_belief(s, org=org_b, brand=brand_b, statement="BRAND-B-ONLY belief that must not leak", confidence=90)
            await s.commit()

        # Brand A: grounded in its OWN two beliefs only.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block, prov = await resolve_strategy_evidence(s, tenant=_tenant(org=org_a, brand=brand_a, user=user_a))
        assert prov.status == "grounded"
        assert prov.belief_count == 2
        statements = {b.statement for b in prov.beliefs}
        assert "Reels beat static for leads" in statements
        assert "BRAND-B-ONLY belief that must not leak" not in statements  # isolation
        assert "Reels beat static for leads" in block
        assert all(0 <= b.confidence <= 100 for b in prov.beliefs)

        # Brand B: grounded in exactly its own one belief (confirms isolation both ways).
        async with AsyncSession(eng, expire_on_commit=False) as s:
            _block_b, prov_b = await resolve_strategy_evidence(s, tenant=_tenant(org=org_b, brand=brand_b, user=user_b))
        assert prov_b.status == "grounded" and prov_b.belief_count == 1
        assert prov_b.beliefs[0].statement == "BRAND-B-ONLY belief that must not leak"

        # A brand with NO beliefs → INSUFFICIENT_EVIDENCE, no fabrication.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            _blk, prov_c = await resolve_strategy_evidence(s, tenant=_tenant(org=org_a, brand=empty_c, user=user_a))
        assert prov_c.status == "insufficient_evidence"
        assert prov_c.belief_count == 0 and prov_c.beliefs == []
        assert "hypothesis" in prov_c.note.lower()
    finally:
        async with eng.begin() as conn:
            for org_id, user_id in ((org_a, user_a), (org_b, user_b)):
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
        await eng.dispose()


@pytest.mark.asyncio
async def test_run_strategy_persists_evidence_grounding(monkeypatch):
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.strategist import service
    from aicmo.modules.strategist.models import MarketingStrategyRecord
    from aicmo.modules.strategist.schemas import MarketingStrategy
    from tests._dbtest import async_dsn
    from tests.strategist.test_strategist import _valid_strategy

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rec_id = uuid.uuid4()
    grounding_payload = {
        "status": "grounded", "belief_count": 1,
        "beliefs": [{"category": "channel", "subject_key": "channel:x",
                     "statement": "Reels beat static", "confidence": 82, "evidence_count": 2}],
        "note": "Grounded in measured outcomes.",
    }
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org, brand=brand, user=user, tag=tag)
            await conn.execute(
                text("INSERT INTO marketing_strategies (id, organization_id, brand_id, user_id, status) "
                     "VALUES (:i,:o,:b,:u,'pending')"),
                {"i": rec_id, "o": org, "b": brand, "u": str(user)})

        # Mock the LLM so no real call happens; run_strategy must persist provenance.
        strategy = MarketingStrategy.model_validate(_valid_strategy())
        monkeypatch.setattr(service, "generate_strategy", AsyncMock(return_value=strategy))

        await service.run_strategy(
            str(rec_id), SimpleNamespace(), "", "", "ACTIVE BELIEFS block", grounding_payload
        )

        async with AsyncSession(eng, expire_on_commit=False) as s:
            row = await s.get(MarketingStrategyRecord, rec_id)
            assert row is not None
            assert row.status == "completed"
            assert row.evidence_grounding is not None
            assert row.evidence_grounding["status"] == "grounded"
            assert row.evidence_grounding["beliefs"][0]["statement"] == "Reels beat static"
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM marketing_strategies WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
