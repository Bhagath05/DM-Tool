"""Phase 7.20 Stage 3f — end-to-end API tenant/brand isolation for Business Economics.

These tests drive the REAL FastAPI app (httpx + ASGITransport) against REAL
PostgreSQL. Only the authenticated identity is injected (via the standard FastAPI
``dependency_overrides[require_user]`` seam — exactly what a signed-in session would
produce); everything downstream (tenant resolution, membership check, brand scope,
RBAC permission computation, RLS context, the service/store) runs for real.

Two isolated, synthetic tenants are created with the real onboarding workspace
service (no real customer data):

    Tenant A: user A (owner) → org A → brand A; economics unit price 65.00
    Tenant B: user B (owner) → org B → brand B; economics unit price 999.00

The tests verify that A cannot read or modify B's profile/economics, that missing
or invalid tenant context fails safe, that a foreign brand is indistinguishable
from a non-existent one (no existence disclosure), that the Opportunity / Strategy
/ Advisor / Coach consumer routes also reject a cross-tenant brand header, and that
RBAC still gates the economics write behind ``settings.manage``.

All synthetic rows are removed in a ``finally`` block, preserving existing data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aicmo.auth.dependencies import AuthContext, require_user
from aicmo.modules.business_dna import economics_store
from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue
from aicmo.modules.business_dna.schemas import ContextProvenance
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.orgs import service as orgs_service
from aicmo.modules.orgs.models import MemberRole, OrganizationMember
from aicmo.modules.orgs.schemas import OnboardingWorkspacePayload
from aicmo.modules.users.models import User
from aicmo.tenancy.context import TenantContext

_ORIGIN = "https://dm-tool-web.vercel.app"


@dataclass
class _Tenant:
    user_id: uuid.UUID
    org_id: uuid.UUID
    brand_id: uuid.UUID
    member_id: uuid.UUID


def _client() -> httpx.AsyncClient:
    from aicmo.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://testserver",
        headers={"origin": _ORIGIN},
    )


def _tenant_ctx(t: _Tenant, *, perms: frozenset[str]) -> TenantContext:
    return TenantContext(
        user_id=str(t.user_id), user_uuid=t.user_id, organization_id=t.org_id,
        brand_id=t.brand_id, member_id=t.member_id, role_slugs=frozenset({"owner"}),
        permissions=perms,
    )


async def _seed_tenant(session: AsyncSession, tag: str, *, price: float) -> _Tenant:
    """Create user → workspace (org+brand+owner member) → profile → economics."""
    user = User(id=uuid.uuid4(), email=f"{tag}-{uuid.uuid4().hex[:6]}@t.local", status="active")
    session.add(user)
    await session.flush()
    result = await orgs_service.create_workspace(
        session,
        actor_user=user,
        payload=OnboardingWorkspacePayload(
            organization_name=f"Org {tag}", organization_slug=f"org-{tag}-{uuid.uuid4().hex[:6]}",
            brand_name=f"Brand {tag}", brand_slug=f"brand-{tag}-{uuid.uuid4().hex[:6]}",
            display_name=None,
        ),
    )
    member = (
        await session.execute(
            text("SELECT id FROM organization_members WHERE organization_id=:o AND user_id=:u"),
            {"o": result.organization_id, "u": user.id},
        )
    ).scalar_one()
    t = _Tenant(user_id=user.id, org_id=result.organization_id, brand_id=result.brand_id, member_id=member)
    session.add(BusinessProfile(
        id=uuid.uuid4(), user_id=f"u-{tag}-{uuid.uuid4().hex[:6]}", business_name=f"B{tag}",
        industry="svc", target_audience="people who value convenience here", brand_tone="friendly",
        organization_id=t.org_id, brand_id=t.brand_id,
    ))
    await session.flush()
    await economics_store.set_economics(
        session, tenant=_tenant_ctx(t, perms=frozenset({"settings.manage"})),
        payload=BusinessEconomics(price=EconomicValue(value=price, provenance=ContextProvenance.USER_STATED, currency="USD")),
    )
    return t


async def _cleanup(engine, tenants: list[_Tenant]) -> None:
    orgs = [t.org_id for t in tenants]
    users = [t.user_id for t in tenants]
    # Delete children before parents (create_workspace writes audit_events, which
    # FK both organizations and brands). One ordered transaction — no table here
    # is optional, so a failure should surface rather than be swallowed.
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM member_roles WHERE member_id IN (SELECT id FROM organization_members WHERE organization_id = ANY(:o))"), {"o": orgs})
        await conn.execute(text("DELETE FROM organization_members WHERE organization_id = ANY(:o)"), {"o": orgs})
        await conn.execute(text("DELETE FROM business_profiles WHERE organization_id = ANY(:o)"), {"o": orgs})
        await conn.execute(text("DELETE FROM audit_events WHERE organization_id = ANY(:o)"), {"o": orgs})
        await conn.execute(text("DELETE FROM brands WHERE organization_id = ANY(:o)"), {"o": orgs})
        await conn.execute(text("DELETE FROM organizations WHERE id = ANY(:o)"), {"o": orgs})
        await conn.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": users})


def _override_as(t: _Tenant) -> None:
    from aicmo.main import app

    app.dependency_overrides[require_user] = lambda: AuthContext(user_id=str(t.user_id), user_uuid=t.user_id)


def _clear_override() -> None:
    from aicmo.main import app

    app.dependency_overrides.pop(require_user, None)


def _hdr(org: uuid.UUID, brand: uuid.UUID) -> dict[str, str]:
    return {"X-Organization-Id": str(org), "X-Brand-Id": str(brand)}


# =========================================================================== #
#  End-to-end isolation across the economics + consumer API surface
# =========================================================================== #


@pytest.mark.asyncio
async def test_economics_api_tenant_isolation_real_pg():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    import aicmo.main  # noqa: F401 — ensure app + models imported

    eng = create_async_engine(async_dsn())
    tenants: list[_Tenant] = []
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _seed_tenant(s, "a", price=65.0)
            b = await _seed_tenant(s, "b", price=999.0)
            await s.commit()
        tenants = [a, b]

        async with _client() as c:
            # 1. Tenant A, own brand → 200 and sees ONLY its own figure (65), never 999.
            _override_as(a)
            r = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, a.brand_id))
            assert r.status_code == 200, r.text
            assert "65" in r.text and "999" not in r.text

            # 2. A cannot read B's economics via B's brand in A's org header → 403 (BrandNotInOrg).
            r = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, b.brand_id))
            assert r.status_code == 403, r.text
            assert "999" not in r.text  # B's figure never leaks

            # 3. A cannot read B's economics by claiming B's org → 403 (TenantMismatch, A not a member).
            r = await c.get("/api/v1/business-dna/economics", headers=_hdr(b.org_id, b.brand_id))
            assert r.status_code == 403, r.text
            assert "999" not in r.text

            # 4. A cannot read B's business profile → 403.
            r = await c.get("/api/v1/business/profile", headers=_hdr(a.org_id, b.brand_id))
            assert r.status_code == 403, r.text

            # 5. Non-disclosure: a foreign brand (B, exists) and a random non-existent brand
            #    return the SAME status — an attacker cannot tell whether the record exists.
            foreign = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, b.brand_id))
            nonexistent = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, uuid.uuid4()))
            assert foreign.status_code == nonexistent.status_code == 403

            # 6. A cannot MODIFY B's economics → 403, and B's stored value is unchanged.
            w = await c.put(
                "/api/v1/business-dna/economics",
                headers=_hdr(a.org_id, b.brand_id),
                json={"price": {"value": 1.0, "provenance": "USER_STATED", "currency": "USD"}},
            )
            assert w.status_code == 403, w.text
            _override_as(b)
            rb = await c.get("/api/v1/business-dna/economics", headers=_hdr(b.org_id, b.brand_id))
            assert rb.status_code == 200 and "999" in rb.text  # untouched

            # 7. Consumers reject a cross-tenant brand header too (A's org, B's brand) → 403.
            _override_as(a)
            for path in (
                "/api/v1/opportunities",
                "/api/v1/strategist/latest",
                "/api/v1/coach/analytics-summary",
                "/api/v1/advisor/readiness",
            ):
                rc = await c.get(path, headers=_hdr(a.org_id, b.brand_id))
                assert rc.status_code == 403, f"{path} -> {rc.status_code}: {rc.text}"

            # 8. Missing tenant context fails safe.
            _clear_override()  # no authenticated identity
            r = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, a.brand_id))
            assert r.status_code == 401, r.text

            # 9. Garbage tenant header → 400 (never a 200/500).
            _override_as(a)
            r = await c.get(
                "/api/v1/business-dna/economics",
                headers={"X-Organization-Id": "<script>alert(1)</script>", "X-Brand-Id": str(a.brand_id)},
            )
            assert r.status_code == 400, r.text
    finally:
        _clear_override()
        if tenants:
            await _cleanup(eng, tenants)
        await eng.dispose()


# =========================================================================== #
#  RBAC: the economics WRITE stays gated behind settings.manage
# =========================================================================== #


@pytest.mark.asyncio
async def test_economics_api_rbac_write_requires_settings_manage_real_pg():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    import aicmo.main  # noqa: F401

    eng = create_async_engine(async_dsn())
    tenants: list[_Tenant] = []
    viewer_id = uuid.uuid4()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _seed_tenant(s, "rbac", price=42.0)
            # Add a VIEWER member to org A: has analytics.view, NOT settings.manage.
            viewer = User(id=viewer_id, email=f"viewer-{uuid.uuid4().hex[:6]}@t.local", status="active")
            s.add(viewer)
            await s.flush()
            role_id = (await s.execute(text("SELECT id FROM roles WHERE slug='viewer'"))).scalar_one()
            vm = OrganizationMember(
                id=uuid.uuid4(), organization_id=a.org_id, user_id=viewer.id,
                last_active_brand_id=a.brand_id,
            )
            s.add(vm)
            await s.flush()
            s.add(MemberRole(id=uuid.uuid4(), member_id=vm.id, role_id=role_id))
            await s.commit()
        tenants = [a]

        async with _client() as c:
            vt = _Tenant(user_id=viewer_id, org_id=a.org_id, brand_id=a.brand_id, member_id=uuid.uuid4())
            _override_as(vt)
            # Viewer CAN read (analytics.view) ...
            rr = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, a.brand_id))
            assert rr.status_code == 200, rr.text
            # ... but CANNOT write economics (needs settings.manage) → 403.
            rw = await c.put(
                "/api/v1/business-dna/economics",
                headers=_hdr(a.org_id, a.brand_id),
                json={"price": {"value": 7.0, "provenance": "USER_STATED", "currency": "USD"}},
            )
            assert rw.status_code == 403, rw.text
            # The owner's figure is unchanged by the denied write.
            _override_as(a)
            chk = await c.get("/api/v1/business-dna/economics", headers=_hdr(a.org_id, a.brand_id))
            assert chk.status_code == 200 and "42" in chk.text
    finally:
        _clear_override()
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM member_roles WHERE member_id IN (SELECT id FROM organization_members WHERE user_id=:u)"), {"u": viewer_id})
            await conn.execute(text("DELETE FROM organization_members WHERE user_id=:u"), {"u": viewer_id})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": viewer_id})
        if tenants:
            await _cleanup(eng, tenants)
        await eng.dispose()
