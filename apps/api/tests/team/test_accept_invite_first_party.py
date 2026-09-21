"""B1 regression — accept-invite must attach the membership to the real
first-party User (identified by User.id), never to a Clerk-era phantom.

Real PostgreSQL. A first-party user has clerk_user_id = NULL; the pre-fix
router looked up `User.clerk_user_id == auth.user_id` (no match) and
lazy-created a phantom user, so the membership never reached the signed-in
user. This test fails against that implementation and passes after the fix.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

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


async def test_accept_invite_attaches_membership_to_first_party_user():
    _pg()
    from aicmo.auth.dependencies import AuthContext
    from aicmo.modules.team import service as team_service
    from aicmo.modules.team.router import accept_invite_endpoint
    from aicmo.modules.team.schemas import InviteAcceptRequest

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    org = uuid.uuid4()
    invitee = uuid.uuid4()
    email = f"invitee-{tag}@example.com"
    raw_token = secrets.token_urlsafe(32)

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            # A genuine first-party user: clerk_user_id IS NULL.
            await s.execute(
                text("INSERT INTO users (id, clerk_user_id, email, status) VALUES (:i,NULL,:e,'active')"),
                {"i": invitee, "e": email},
            )
            await s.execute(
                text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                {"i": org, "s": f"org-{tag}", "n": "Invite Org", "o": invitee},
            )
            await s.execute(
                text(
                    "INSERT INTO organization_invite "
                    "(id, organization_id, email, role_slug, token_hash, status, expires_at) "
                    "VALUES (:i,:o,:e,'editor',:th,'pending',:exp)"
                ),
                {
                    "i": uuid.uuid4(), "o": org, "e": email,
                    "th": team_service.hash_token(raw_token),
                    "exp": datetime.now(UTC) + timedelta(days=3),
                },
            )
            await s.commit()

        auth = AuthContext(
            user_id=str(invitee), user_uuid=invitee, session_id=str(uuid.uuid4()), email=email
        )
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp = await accept_invite_endpoint(
                InviteAcceptRequest(token=raw_token), auth=auth, session=s
            )
            await s.commit()
        assert resp is not None

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # Membership is on the REAL user id.
            member = (
                await s.execute(
                    text(
                        "SELECT user_id FROM organization_members "
                        "WHERE organization_id=:o AND status='active'"
                    ),
                    {"o": org},
                )
            ).all()
            assert [r[0] for r in member] == [invitee]
            # No phantom user was created (pre-fix used clerk_user_id=str(user.id)).
            phantom = (
                await s.execute(
                    text("SELECT count(*) FROM users WHERE clerk_user_id=:c"),
                    {"c": str(invitee)},
                )
            ).scalar_one()
            assert phantom == 0
            # There is exactly ONE user row for this person.
            total = (
                await s.execute(
                    text("SELECT count(*) FROM users WHERE id=:i OR email=:e"),
                    {"i": invitee, "e": email},
                )
            ).scalar_one()
            assert total == 1
            # Invite consumed by the real user.
            acc = (
                await s.execute(
                    text("SELECT status, accepted_by_user_id FROM organization_invite WHERE organization_id=:o"),
                    {"o": org},
                )
            ).one()
            assert acc[0] == "accepted" and acc[1] == invitee
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM member_roles WHERE member_id IN (SELECT id FROM organization_members WHERE organization_id=:o)"), {"o": org})
            await conn.execute(text("DELETE FROM organization_members WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organization_invite WHERE organization_id=:o"), {"o": org})
            # audit_events rows CASCADE when the organization is deleted.
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:i OR clerk_user_id=:c"), {"i": invitee, "c": str(invitee)})
        await eng.dispose()
