"""Phase 7.20 Stage 3 — read-only facet accessor `get_economics_facet`.

The "request only the facet you need" seam consumers use instead of building the
full Business DNA. Proves facet selection, provenance preservation, honest
missing/insufficient states, determinism, no DB writes, brand requirement, and
(real Postgres) brand isolation.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aicmo.modules.business_dna import service as dna_service
from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue
from aicmo.modules.business_dna.schemas import ContextProvenance, FacetStatus
from aicmo.tenancy.context import TenantContext

_ORG, _BRAND = uuid.uuid4(), uuid.uuid4()


def _tenant(*, brand=_BRAND):
    return TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(), organization_id=_ORG,
        brand_id=brand, member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}),
        permissions=frozenset({"analytics.view"}),
    )


def _profile_row(**econ_fields) -> SimpleNamespace:
    row = SimpleNamespace(
        business_location="Austin, TX", monthly_budget_band="$100-500",
        pricing="$65 full groom", primary_goal_text="200 bookings/mo",
        products=["Full groom"], services=["Bath"],
    )
    for k, v in econ_fields.items():
        setattr(row, k, v)
    return row


@pytest.mark.asyncio
async def test_accessor_returns_economics_facet_only(monkeypatch):
    async def _fake_profile(session, brand_id):
        return _profile_row()

    monkeypatch.setattr("aicmo.modules.onboarding.service.get_profile_or_none", _fake_profile)
    facet = await dna_service.get_economics_facet(object(), tenant=_tenant())
    assert facet.key == "economics" and facet.title == "Business Economics"
    assert facet.status == FacetStatus.POPULATED  # budget/pricing are USER_STATED
    assert any(i.provenance == ContextProvenance.USER_STATED for i in facet.items)


@pytest.mark.asyncio
async def test_accessor_preserves_economics_provenance(monkeypatch):
    """A stored USER_STATED price flows through the facet with its provenance and
    is NOT upgraded; computed metrics (margin) are SYSTEM_INFERRED, never VERIFIED."""
    econ = BusinessEconomics(
        currency="USD",
        price=EconomicValue(value=100.0, provenance=ContextProvenance.USER_STATED),
        unit_cost=EconomicValue(value=40.0, provenance=ContextProvenance.USER_STATED),
    )
    row = _profile_row(economics=econ.model_dump(mode="json"))

    async def _fake_profile(session, brand_id):
        return row

    monkeypatch.setattr("aicmo.modules.onboarding.service.get_profile_or_none", _fake_profile)
    facet = await dna_service.get_economics_facet(object(), tenant=_tenant())
    by = {i.label: i for i in facet.items}
    assert by["Unit price"].provenance == ContextProvenance.USER_STATED
    gm = by["Gross margin"]
    assert gm.provenance == ContextProvenance.SYSTEM_INFERRED and gm.detail == "60.0%"


@pytest.mark.asyncio
async def test_accessor_unknown_when_no_profile(monkeypatch):
    async def _none(session, brand_id):
        return None

    monkeypatch.setattr("aicmo.modules.onboarding.service.get_profile_or_none", _none)
    facet = await dna_service.get_economics_facet(object(), tenant=_tenant())
    assert facet.status == FacetStatus.UNKNOWN


@pytest.mark.asyncio
async def test_accessor_requires_brand():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await dna_service.get_economics_facet(object(), tenant=_tenant(brand=None))
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_accessor_is_deterministic_and_writes_nothing(monkeypatch):
    async def _fake_profile(session, brand_id):
        return _profile_row()

    monkeypatch.setattr("aicmo.modules.onboarding.service.get_profile_or_none", _fake_profile)
    guard = MagicMock(name="session")
    for m in ("add", "add_all", "delete", "flush", "commit", "merge"):
        getattr(guard, m).side_effect = AssertionError(f"session.{m} must not be called")
    a = await dna_service.get_economics_facet(guard, tenant=_tenant())
    b = await dna_service.get_economics_facet(guard, tenant=_tenant())
    assert a.model_dump() == b.model_dump()  # deterministic


@pytest.mark.asyncio
async def test_accessor_brand_isolation_real_pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.business_dna import economics_store as store
    from aicmo.modules.onboarding.models import BusinessProfile
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    oa, ba, ua = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ob, bb, ub = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def ten(*, org, brand, user):
        return TenantContext(
            user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
            member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}),
            permissions=frozenset({"analytics.view", "settings.manage"}),
        )

    try:
        async with eng.begin() as conn:
            for org, brand, user, tag in ((oa, ba, ua, ta), (ob, bb, ub, tb)):
                await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                                   {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
                await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                                   {"i": org, "s": f"o{tag}", "n": "O", "o": user})
                await conn.execute(text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                                   {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})
        async with AsyncSession(eng, expire_on_commit=False) as s:
            for org, brand, tag in ((oa, ba, ta), (ob, bb, tb)):
                s.add(BusinessProfile(
                    id=uuid.uuid4(), user_id=f"u-{tag}", business_name="B", industry="svc",
                    target_audience="people who value convenience here", brand_tone="friendly",
                    organization_id=org, brand_id=brand))
            await s.commit()
            await store.set_economics(s, tenant=ten(org=oa, brand=ba, user=ua),
                                      payload=BusinessEconomics(price=EconomicValue(value=65.0, provenance=ContextProvenance.USER_STATED)))

        async with AsyncSession(eng, expire_on_commit=False) as s:
            facet_a = await dna_service.get_economics_facet(s, tenant=ten(org=oa, brand=ba, user=ua))
            facet_b = await dna_service.get_economics_facet(s, tenant=ten(org=ob, brand=bb, user=ub))
        a_labels = {i.label: i.detail for i in facet_a.items}
        assert any("65.00" in (v or "") for v in a_labels.values())  # A has its price
        assert not any("65.00" in (i.detail or "") for i in facet_b.items)  # B never sees A's
    finally:
        async with eng.begin() as conn:
            for org, user in ((oa, ua), (ob, ub)):
                await conn.execute(text("DELETE FROM business_profiles WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
