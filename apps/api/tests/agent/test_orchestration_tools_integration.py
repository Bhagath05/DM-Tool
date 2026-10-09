"""Phase 7.1 — orchestration tools, real-Postgres integration.

Proves the database-backed security invariant that unit mocks cannot: the
registry tools return ONLY the tenant-brand's rows. Seeds a strategy for brand
A and brand B and asserts get_marketing_strategy (executed through the registry)
returns A's strategy for A and B's for B — never the other's. Also exercises
get_experiments end-to-end over the real DB for a brand with no experiments
(honest empty, not fabricated).

Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid

import pytest


def _ctx(session, *, org, brand, user):
    from aicmo.agent.types import ExecutionContext
    from aicmo.tenancy.context import TenantContext

    tenant = TenantContext(
        user_id=str(user),
        user_uuid=user,
        organization_id=org,
        brand_id=brand,
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view", "library.view"}),
    )
    return ExecutionContext(session=session, tenant=tenant)


@pytest.mark.asyncio
async def test_strategy_and_experiments_tools_are_brand_isolated_over_real_db():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph
    from aicmo.agent.tools import get_default_registry
    from aicmo.modules.strategist.models import MarketingStrategyRecord
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org = uuid.uuid4()
    brand_a, brand_b = uuid.uuid4(), uuid.uuid4()
    user = uuid.uuid4()
    reg = get_default_registry()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"},
            )
            await s.execute(
                text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                {"i": org, "s": f"o{tag}", "n": "O", "o": user},
            )
            for bid, slug in ((brand_a, f"a{tag}"), (brand_b, f"b{tag}")):
                await s.execute(
                    text(
                        "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
                        "VALUES (:i,:o,:s,:n,:u)"
                    ),
                    {"i": bid, "o": org, "s": slug, "n": slug, "u": user},
                )
            for bid, tag_txt in ((brand_a, "ALPHA_POSITIONING"), (brand_b, "BETA_POSITIONING")):
                s.add(MarketingStrategyRecord(
                    id=uuid.uuid4(), organization_id=org, brand_id=bid, user_id=str(user),
                    status="completed",
                    strategy={
                        "positioning": f"{tag_txt} bakery for locals",
                        "target_summary": "nearby workers",
                        "recommendation": "Publish a lead page",
                    },
                ))
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # --- strategy tool isolation (end-to-end through the registry) ---
            res_a = await reg.execute_tool(
                "get_marketing_strategy", {}, _ctx(s, org=org, brand=brand_a, user=user)
            )
            res_b = await reg.execute_tool(
                "get_marketing_strategy", {}, _ctx(s, org=org, brand=brand_b, user=user)
            )
            assert res_a.data.present is True
            assert "ALPHA_POSITIONING" in (res_a.data.positioning or "")
            assert "BETA_POSITIONING" not in (res_a.data.positioning or "")
            assert "BETA_POSITIONING" in (res_b.data.positioning or "")
            assert "ALPHA_POSITIONING" not in (res_b.data.positioning or "")

            # --- experiments tool: honest empty over the real DB (none seeded) ---
            res_exp = await reg.execute_tool(
                "get_experiments", {"limit": 10}, _ctx(s, org=org, brand=brand_a, user=user)
            )
            assert res_exp.data.items == []  # not fabricated
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM marketing_strategies WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
