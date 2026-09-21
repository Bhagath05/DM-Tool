"""B3 regression — social OAuth callback must resolve the tenant for a
first-party user (clerk_user_id = NULL) by internal User.id carried in the
signed state.

Real PostgreSQL, real signed-state issue/verify + resolve_tenant_for_oauth.
Pre-fix the callback looked up `User.clerk_user_id == user_id` (NULL for
first-party) and returned 404. This test fails against that and passes after
the fix. OAuth state security (sign/verify/expiry/nonce) is unchanged and
still exercised end-to-end.
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


async def test_oauth_callback_resolves_first_party_user_by_internal_id():
    _pg()
    from aicmo.modules.social import service as social_service
    from aicmo.modules.social.oauth_state import issue, verify

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            # A genuine first-party user: clerk_user_id IS NULL.
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": user, "e": f"social-{tag}@example.com"},
            )
            await s.execute(
                text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                {"i": org, "s": f"org-{tag}", "n": "Social Org", "o": user},
            )
            await s.execute(
                text(
                    "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id, status) "
                    "VALUES (:i,:o,:s,:n,:u,'active')"
                ),
                {"i": brand, "o": org, "s": f"brand-{tag}", "n": "Brand", "u": user},
            )
            await s.execute(
                text(
                    "INSERT INTO organization_members (id, organization_id, user_id, status) "
                    "VALUES (:i,:o,:u,'active')"
                ),
                {"i": uuid.uuid4(), "o": org, "u": user},
            )
            await s.commit()

        # Signed state carries the internal DM User.id (str), exactly as the
        # connect endpoint issues it (user_id=tenant.user_id = str(user.id)).
        state = issue(user_id=str(user), brand_id=str(brand), platform="instagram")
        uid, bid, platform = verify(state)
        assert uid == str(user) and platform == "instagram"

        async with AsyncSession(eng, expire_on_commit=False) as s:
            tenant = await social_service.resolve_tenant_for_oauth(
                s, user_id=uid, brand_id=uuid.UUID(bid)
            )
        assert tenant.user_uuid == user
        assert tenant.user_id == str(user)
        assert tenant.brand_id == brand
        assert tenant.organization_id == org
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM organization_members WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
