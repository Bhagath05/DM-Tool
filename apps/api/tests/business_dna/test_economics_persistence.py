"""Phase 7.20 Stage 2b — Business Economics persistence (real Postgres).

Proves the additive ``business_profiles.economics`` JSONB column: persistence +
retrieval, provenance preservation, the no-LLM-overwrite merge, tenant/brand
isolation, that re-analysis cannot erase economics (and economics never touches
``analysis``), and that the migration is reversible. Skips cleanly when no
project Postgres is reachable.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue
from aicmo.modules.business_dna.schemas import ContextProvenance


def _tenant(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view", "settings.manage"}),
    )


def _ev(value: float, provenance: ContextProvenance, *, currency: str | None = "USD") -> EconomicValue:
    return EconomicValue(value=value, provenance=provenance, currency=currency, source="test")


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                       {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
    await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                       {"i": org, "s": f"o{tag}", "n": "O", "o": user})
    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})


async def _seed_profile(session, *, org, brand, tag):
    from aicmo.modules.onboarding.models import BusinessProfile

    p = BusinessProfile(
        id=uuid.uuid4(), user_id=f"u-{tag}-{uuid.uuid4().hex[:6]}",
        business_name="PawPals", industry="mobile dog grooming",
        target_audience="busy suburban dog owners who value convenience",
        brand_tone="friendly", organization_id=org, brand_id=brand,
    )
    session.add(p)
    await session.flush()
    return p


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def _cleanup(eng, orgs_users):
    from sqlalchemy import text

    async with eng.begin() as conn:
        for org_id, user_id in orgs_users:
            await conn.execute(text("DELETE FROM business_profiles WHERE organization_id=:o"), {"o": org_id})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
    await eng.dispose()


@pytest.mark.asyncio
async def test_persist_update_overwrite_isolation_and_reanalysis():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text, update
    from sqlalchemy.ext.asyncio import AsyncSession

    import aicmo.main  # noqa: F401  (register ORM models)
    from aicmo.modules.business_dna import economics_store as store
    from aicmo.modules.onboarding.models import BusinessProfile

    eng = _engine()
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ten_a = _tenant(org=org_a, brand=brand_a, user=user_a)
    ten_b = _tenant(org=org_b, brand=brand_b, user=user_b)
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_profile(s, org=org_a, brand=brand_a, tag=ta)
            await _seed_profile(s, org=org_b, brand=brand_b, tag=tb)
            await s.commit()

        # 1) Persist + retrieve, provenance preserved. Partial payload is fine.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            saved = await store.set_economics(
                s, tenant=ten_a,
                payload=BusinessEconomics(
                    currency="USD", reporting_period="monthly",
                    price=_ev(65.0, ContextProvenance.USER_STATED),
                    unit_cost=_ev(25.0, ContextProvenance.USER_STATED),
                    fixed_costs=_ev(5000.0, ContextProvenance.USER_STATED),
                ),
            )
            assert saved.price is not None and saved.price.value == 65.0
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await store.get_economics(s, tenant=ten_a)
        assert got is not None
        assert got.price.value == 65.0 and got.price.provenance == ContextProvenance.USER_STATED
        assert got.currency == "USD" and got.unit_cost.value == 25.0
        assert got.avg_order_value is None  # missing value stays honestly absent

        # 2) No-LLM-overwrite: a SYSTEM_INFERRED value cannot clobber USER_STATED.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await store.set_economics(
                s, tenant=ten_a,
                payload=BusinessEconomics(price=_ev(9999.0, ContextProvenance.SYSTEM_INFERRED)),
            )
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await store.get_economics(s, tenant=ten_a)
        assert got.price.value == 65.0  # protected — unchanged
        # A USER_STATED correction DOES apply; VERIFIED also overwrites.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await store.set_economics(s, tenant=ten_a, payload=BusinessEconomics(price=_ev(70.0, ContextProvenance.USER_STATED)))
            await store.set_economics(s, tenant=ten_a, payload=BusinessEconomics(price=_ev(72.0, ContextProvenance.VERIFIED)))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await store.get_economics(s, tenant=ten_a)
        assert got.price.value == 72.0 and got.price.provenance == ContextProvenance.VERIFIED
        # And now a SYSTEM_INFERRED value still cannot clobber the VERIFIED one.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await store.set_economics(s, tenant=ten_a, payload=BusinessEconomics(price=_ev(1.0, ContextProvenance.SYSTEM_INFERRED)))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await store.get_economics(s, tenant=ten_a)
        assert got.price.value == 72.0

        # 3) Tenant + brand isolation: brand B has no economics; its own write is separate.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            assert await store.get_economics(s, tenant=ten_b) is None
            await store.set_economics(s, tenant=ten_b, payload=BusinessEconomics(price=_ev(10.0, ContextProvenance.USER_STATED)))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got_a = await store.get_economics(s, tenant=ten_a)
            got_b = await store.get_economics(s, tenant=ten_b)
        assert got_a.price.value == 72.0 and got_b.price.value == 10.0  # no cross-brand bleed

        # 4) Re-analysis cannot erase economics, and economics never touched analysis.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(
                update(BusinessProfile)
                .where(BusinessProfile.brand_id == brand_a)
                .values(analysis={"business_summary": "re-run"}, analysis_status="completed", analysis_error=None)
            )
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await store.get_economics(s, tenant=ten_a)
            analysis = (await s.execute(
                text("SELECT analysis->>'business_summary' FROM business_profiles WHERE brand_id=:b"), {"b": brand_a}
            )).scalar_one()
        assert got is not None and got.price.value == 72.0  # survived re-analysis
        assert analysis == "re-run"  # analysis updated independently
    finally:
        await _cleanup(eng, [(org_a, user_a), (org_b, user_b)])


def test_migration_0082_is_reversible():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    import importlib.util
    import pathlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text

    from tests._dbtest import async_dsn

    path = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0082_business_profiles_economics.py"
    spec = importlib.util.spec_from_file_location("mig0082", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)  # type: ignore[union-attr]
    assert mig.revision == "0082_business_profiles_economics"
    assert mig.down_revision == "0081_strategy_evidence_grounding"

    eng = create_engine(async_dsn())  # +psycopg → sync psycopg3 engine

    def _has_col(conn) -> bool:
        return conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='business_profiles' AND column_name='economics'"
            )
        ).first() is not None

    try:
        with eng.connect() as conn:
            trans = conn.begin()
            mig.op = Operations(MigrationContext.configure(connection=conn))  # bind the proxy
            assert _has_col(conn)        # migration already applied to the test DB
            mig.downgrade()
            assert not _has_col(conn)    # reversible: column dropped
            mig.upgrade()
            assert _has_col(conn)        # and re-added
            trans.rollback()             # leave the shared schema exactly as it was
    finally:
        eng.dispose()
