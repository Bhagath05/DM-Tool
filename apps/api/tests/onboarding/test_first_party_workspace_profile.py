"""B2 regression — onboarding workspace + BusinessProfile creation must
succeed for a first-party user (clerk_user_id = NULL) and stamp
BusinessProfile.user_id with the internal User.id.

Real PostgreSQL, real `create_workspace` service path. Pre-fix, the profile
row was inserted with `actor_user.clerk_user_id` (NULL) into a NOT-NULL unique
column, raising IntegrityError and rolling back the whole workspace. This test
exercises the full transaction (org + brand + member + role + profile), not a
helper in isolation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


def _pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def test_first_party_workspace_creates_profile_with_internal_user_id():
    _pg()
    from aicmo.modules.orgs import service as orgs_service
    from aicmo.modules.orgs.schemas import OnboardingWorkspacePayload
    from aicmo.modules.users.models import User

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    org_id = None

    payload = OnboardingWorkspacePayload(
        organization_name="Acme",
        organization_slug=f"acme-{tag}",
        brand_name="Acme Espresso",
        brand_slug=f"acme-espresso-{tag}",
        display_name="Owner",
        industry="Cafe / Restaurant",
        website="https://acme.example",
        brand_description="Specialty coffee for office mornings",
        target_audience="Young professionals who buy coffee on the way to work",
        primary_goal="leads",
        preferred_platforms=["instagram", "google"],
        brand_tone="friendly",
    )

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            # A genuine first-party user: clerk_user_id IS NULL.
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": user_id, "e": f"owner-{tag}@example.com"},
            )
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            actor = await s.get(User, user_id)
            assert actor is not None and actor.clerk_user_id is None
            result = await orgs_service.create_workspace(s, actor_user=actor, payload=payload)
            await s.commit()
            org_id = result.organization_id

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # The whole workspace committed (org + brand + member).
            assert (
                await s.execute(text("SELECT count(*) FROM organizations WHERE id=:o"), {"o": org_id})
            ).scalar_one() == 1
            assert (
                await s.execute(
                    text("SELECT count(*) FROM organization_members WHERE organization_id=:o AND status='active'"),
                    {"o": org_id},
                )
            ).scalar_one() == 1
            # BusinessProfile was created and stamped with the INTERNAL User.id.
            prof = (
                await s.execute(
                    text("SELECT user_id FROM business_profiles WHERE organization_id=:o"),
                    {"o": org_id},
                )
            ).one()
            assert prof[0] == str(user_id)
    finally:
        async with eng.begin() as conn:
            if org_id is not None:
                await conn.execute(text("DELETE FROM business_profiles WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM member_roles WHERE member_id IN (SELECT id FROM organization_members WHERE organization_id=:o)"), {"o": org_id})
                await conn.execute(text("DELETE FROM organization_members WHERE organization_id=:o"), {"o": org_id})
                # audit_events rows CASCADE when the organization is deleted.
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
            await conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user_id})
        await eng.dispose()
