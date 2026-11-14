"""Phase 7.20 Stage 3g — authenticated API WRITE-PATH tenant isolation.

Verifies that authenticated POST/PATCH endpoints cannot create, modify, execute or
expose data across tenant boundaries. Reuses the Stage 3f real-PostgreSQL API
isolation harness (``test_economics_api_tenant_isolation``) — the real FastAPI app,
the ``dependency_overrides[require_user]`` identity seam, the ``create_workspace``
tenant seeder and the row cleanup — rather than a parallel framework.

External side effects are mocked (the strategist background LLM task; the coach LLM
router) while authentication, RBAC, tenant resolution and DB persistence stay REAL.
No real integration is invoked, nothing is published, no consequential action runs.

Endpoints covered:
  POST   /api/v1/strategist/generate        (content.create)
  POST   /api/v1/coach/reality-check        (analytics.view)
  POST   /api/v1/advisor/execute            (analytics.view) — IDOR via body id
  POST   /api/v1/advisor/execute/schedule   (content.create) — IDOR via body id
  PATCH  /api/v1/advisor/recommendations/{id} (analytics.view) — IDOR via path id
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aicmo.modules.advisor.models import AdvisorRecommendation
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.orgs.models import MemberRole, OrganizationMember
from aicmo.modules.users.models import User

# Reuse the Stage 3f harness verbatim — do NOT reimplement it.
from tests.business_dna.test_economics_api_tenant_isolation import (
    _cleanup,
    _clear_override,
    _client,
    _hdr,
    _override_as,
    _seed_tenant,
    _Tenant,
)

_HINT = {"target": "content", "format": "social_post", "platform": "Instagram", "goal": "Drive engagement"}


async def _seed_recommendation(session: AsyncSession, t: _Tenant, *, with_hint: bool, status: str = "not_started") -> uuid.UUID:
    rid = uuid.uuid4()
    session.add(AdvisorRecommendation(
        id=rid, organization_id=t.org_id, brand_id=t.brand_id,
        user_id=f"u-{uuid.uuid4().hex[:8]}", record_type="opportunity",
        title="Synthetic recommendation", status=status,
        source_surface="intelligence_hero", source_fingerprint=uuid.uuid4().hex,
        generator_hint=_HINT if with_hint else None,
    ))
    await session.flush()
    return rid


async def _enrich_profile(session: AsyncSession, *, brand_id: uuid.UUID) -> None:
    """Fill the list fields the full BusinessProfileResponse requires (min_length=1)
    so the coach/strategist read path (which validates the response schema) accepts
    the synthetic profile the 3f seeder creates. Test-data completeness only."""
    row = (await session.execute(select(BusinessProfile).where(BusinessProfile.brand_id == brand_id))).scalar_one()
    row.goals = ["Grow bookings"]
    row.preferred_platforms = ["instagram"]
    await session.flush()


async def _add_viewer(session: AsyncSession, *, org_id: uuid.UUID, brand_id: uuid.UUID) -> uuid.UUID:
    """A viewer member of ``org_id``: has analytics.view, NOT content.create."""
    viewer = User(id=uuid.uuid4(), email=f"wview-{uuid.uuid4().hex[:6]}@t.local", status="active")
    session.add(viewer)
    await session.flush()
    role_id = (await session.execute(text("SELECT id FROM roles WHERE slug='viewer'"))).scalar_one()
    vm = OrganizationMember(id=uuid.uuid4(), organization_id=org_id, user_id=viewer.id, last_active_brand_id=brand_id)
    session.add(vm)
    await session.flush()
    session.add(MemberRole(id=uuid.uuid4(), member_id=vm.id, role_id=role_id))
    await session.flush()
    return viewer.id


async def _count(engine, sql: str, **params) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


async def _purge_write_children(engine, orgs: list[uuid.UUID], extra_users: list[uuid.UUID] | None = None) -> None:
    """Remove rows my tests create that FK organizations/brands, before the 3f
    cleanup drops brands/orgs. Also removes any extra (viewer) users + members."""
    async with engine.begin() as conn:
        for tbl in ("scheduled_posts", "content_assets", "advisor_recommendations", "marketing_strategies"):
            await conn.execute(text(f"DELETE FROM {tbl} WHERE organization_id = ANY(:o)"), {"o": orgs})
        if extra_users:
            await conn.execute(text("DELETE FROM member_roles WHERE member_id IN (SELECT id FROM organization_members WHERE user_id = ANY(:u))"), {"u": extra_users})
            await conn.execute(text("DELETE FROM organization_members WHERE user_id = ANY(:u)"), {"u": extra_users})
            await conn.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": extra_users})


# =========================================================================== #
#  Advisor write path — IDOR via a body/path recommendation id
# =========================================================================== #


@pytest.mark.asyncio
async def test_advisor_write_path_idor_real_pg():
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    import aicmo.main  # noqa: F401

    eng = create_async_engine(async_dsn())
    tenants: list[_Tenant] = []
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _seed_tenant(s, "wa", price=10.0)
            b = await _seed_tenant(s, "wb", price=20.0)
            rec_b = await _seed_recommendation(s, b, with_hint=True)              # B's executable rec
            rec_a_nohint = await _seed_recommendation(s, a, with_hint=False)      # A's own, not executable
            await s.commit()
        tenants = [a, b]

        async with _client() as c:
            _override_as(a)

            # 1. A executes B's recommendation id (A's own valid headers) → 404,
            #    no foreign data leaked, no consequential action.
            r = await c.post("/api/v1/advisor/execute", headers=_hdr(a.org_id, a.brand_id),
                             json={"recommendation_id": str(rec_b)})
            assert r.status_code == 404, r.text
            assert "20" not in r.text and str(b.brand_id) not in r.text

            # 2. Control (safe): A executes its OWN rec that has no generator hint →
            #    422 (found + scoped) and the service returns BEFORE any generation.
            r = await c.post("/api/v1/advisor/execute", headers=_hdr(a.org_id, a.brand_id),
                             json={"recommendation_id": str(rec_a_nohint)})
            assert r.status_code == 422, r.text

            # 3. A PATCHes B's recommendation status → 404; B's row is unchanged.
            r = await c.patch(f"/api/v1/advisor/recommendations/{rec_b}",
                              headers=_hdr(a.org_id, a.brand_id), json={"status": "in_progress"})
            assert r.status_code == 404, r.text

            # 4. A schedules a post from B's recommendation id → 404; nothing scheduled.
            r = await c.post("/api/v1/advisor/execute/schedule", headers=_hdr(a.org_id, a.brand_id),
                             json={"recommendation_id": str(rec_b), "platform": "instagram",
                                   "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()})
            assert r.status_code == 404, r.text

        # No writes crossed the boundary: B's rec still exists + unchanged status;
        # no content assets or scheduled posts were created for either brand.
        assert await _count(eng, "SELECT count(*) FROM advisor_recommendations WHERE id=:i AND status='not_started'", i=rec_b) == 1
        assert await _count(eng, "SELECT count(*) FROM scheduled_posts WHERE organization_id = ANY(:o)", o=[a.org_id, b.org_id]) == 0
        assert await _count(eng, "SELECT count(*) FROM content_assets WHERE organization_id = ANY(:o)", o=[a.org_id, b.org_id]) == 0
    finally:
        _clear_override()
        if tenants:
            await _purge_write_children(eng, [t.org_id for t in tenants])
            await _cleanup(eng, tenants)
        await eng.dispose()


# =========================================================================== #
#  Strategist generate — header isolation, missing/invalid ctx, RBAC, control
# =========================================================================== #


@pytest.mark.asyncio
async def test_strategist_generate_tenant_isolation_real_pg(monkeypatch):
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    import aicmo.main  # noqa: F401

    # Mock the background LLM task so no real model call is made by the control case.
    ran: dict = {"calls": 0}

    async def _noop_run_strategy(*a, **k):
        ran["calls"] += 1

    monkeypatch.setattr("aicmo.modules.strategist.service.run_strategy", _noop_run_strategy)

    eng = create_async_engine(async_dsn())
    tenants: list[_Tenant] = []
    viewer_id: uuid.UUID | None = None
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _seed_tenant(s, "sa", price=10.0)
            b = await _seed_tenant(s, "sb", price=20.0)
            await _enrich_profile(s, brand_id=a.brand_id)  # control reaches the profile read
            viewer_id = await _add_viewer(s, org_id=a.org_id, brand_id=a.brand_id)
            await s.commit()
        tenants = [a, b]

        async with _client() as c:
            # 1. Cross-tenant: A authenticated, B's brand header → 403; no record for B.
            _override_as(a)
            r = await c.post("/api/v1/strategist/generate", headers=_hdr(a.org_id, b.brand_id), json={})
            assert r.status_code == 403, r.text

            # 2. Missing tenant context (no identity) → 401.
            _clear_override()
            r = await c.post("/api/v1/strategist/generate", headers=_hdr(a.org_id, a.brand_id), json={})
            assert r.status_code == 401, r.text

            # 3. Invalid tenant header → 400.
            _override_as(a)
            r = await c.post("/api/v1/strategist/generate",
                             headers={"X-Organization-Id": "not-a-uuid", "X-Brand-Id": str(a.brand_id)}, json={})
            assert r.status_code == 400, r.text

            # 4. Insufficient permission: viewer lacks content.create → 403.
            _override_as(_Tenant(user_id=viewer_id, org_id=a.org_id, brand_id=a.brand_id, member_id=uuid.uuid4()))
            r = await c.post("/api/v1/strategist/generate", headers=_hdr(a.org_id, a.brand_id), json={})
            assert r.status_code == 403, r.text

            # 5. Valid control (owner A): 201 and a pending record is created ONLY for A.
            _override_as(a)
            r = await c.post("/api/v1/strategist/generate", headers=_hdr(a.org_id, a.brand_id), json={})
            assert r.status_code == 201, r.text

        # No strategy record leaked to B; exactly one created for A; LLM task mocked.
        assert await _count(eng, "SELECT count(*) FROM marketing_strategies WHERE brand_id=:b", b=b.brand_id) == 0
        assert await _count(eng, "SELECT count(*) FROM marketing_strategies WHERE brand_id=:b", b=a.brand_id) == 1
    finally:
        _clear_override()
        if tenants:
            await _purge_write_children(eng, [t.org_id for t in tenants], extra_users=[viewer_id] if viewer_id else None)
            await _cleanup(eng, tenants)
        await eng.dispose()


# =========================================================================== #
#  Coach reality-check — header isolation + mocked-LLM control
# =========================================================================== #


@pytest.mark.asyncio
async def test_coach_reality_check_tenant_isolation_real_pg(monkeypatch):
    from tests._dbtest import async_dsn, pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    import aicmo.main  # noqa: F401

    # Mock the LLM so the control case makes no external call (reality.py degrades
    # to a deterministic fallback narrative when the router fails).
    class _FakeRouter:
        async def generate(self, *a, **k):
            raise RuntimeError("no LLM in unit test")

    monkeypatch.setattr("aicmo.modules.coach.reality.get_llm_router", lambda: _FakeRouter())

    eng = create_async_engine(async_dsn())
    tenants: list[_Tenant] = []
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _seed_tenant(s, "ca", price=10.0)
            b = await _seed_tenant(s, "cb", price=20.0)
            await _enrich_profile(s, brand_id=a.brand_id)  # control reaches the profile read
            await s.commit()
        tenants = [a, b]

        body = {"goal_text": "Get 50 new customers in 90 days"}
        async with _client() as c:
            _override_as(a)
            # 1. Cross-tenant: A with B's brand header → 403 (before any evaluation).
            r = await c.post("/api/v1/coach/reality-check", headers=_hdr(a.org_id, b.brand_id), json=body)
            assert r.status_code == 403, r.text

            # 2. Missing context → 401.
            _clear_override()
            r = await c.post("/api/v1/coach/reality-check", headers=_hdr(a.org_id, a.brand_id), json=body)
            assert r.status_code == 401, r.text

            # 3. Valid control (owner A) with LLM mocked → 200, advisory only (no writes).
            _override_as(a)
            r = await c.post("/api/v1/coach/reality-check", headers=_hdr(a.org_id, a.brand_id), json=body)
            assert r.status_code == 200, r.text
            assert "feasibility_score" in r.text
    finally:
        _clear_override()
        if tenants:
            await _purge_write_children(eng, [t.org_id for t in tenants])
            await _cleanup(eng, tenants)
        await eng.dispose()
