"""Phase 2 — conversation persistence + tenant isolation (Postgres-gated)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from aicmo.modules.agent import service
from aicmo.modules.agent.models import AgentMessage


class _FakeTenant:
    def __init__(self, *, org, brand, user):
        self.organization_id = org
        self.brand_id = brand
        self.user_uuid = user
        self.user_id = str(user)
        self.role_slugs = frozenset()
        self.permissions = frozenset({"analytics.view"})

    def has_permission(self, slug):
        return slug in self.permissions


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def _seed(session, *, org, brand, user, tag):
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
        {"i": user, "c": f"clerk_{tag}", "e": f"{tag}@t.local"},
    )
    await session.execute(
        text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
        {"i": org, "s": f"org-{tag}", "n": "Agent Org", "o": user},
    )
    await session.execute(
        text(
            "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
            "VALUES (:i,:o,:s,:n,:u)"
        ),
        {"i": brand, "o": org, "s": f"brand-{tag}", "n": "Agent Brand", "u": user},
    )
    await session.flush()


@pytest.mark.asyncio
async def test_conversation_crud_ordering_and_tenant_isolation():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t_a = _FakeTenant(org=org_a, brand=brand_a, user=user_a)
    t_b = _FakeTenant(org=org_b, brand=brand_b, user=user_b)
    convo_id = None
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed(s, org=org_a, brand=brand_a, user=user_a, tag=f"a{tag}")
            await _seed(s, org=org_b, brand=brand_b, user=user_b, tag=f"b{tag}")
            # create + retrieve
            convo = await service.create_conversation(s, tenant=t_a, title="Q1")
            convo_id = convo.id
            got = await service.get_conversation(s, tenant=t_a, conversation_id=convo.id)
            assert got.id == convo.id and got.brand_id == brand_a
            # add ordered messages
            for i, (role, body) in enumerate([("user", "hi"), ("assistant", "hello"), ("user", "more")], start=1):
                s.add(
                    AgentMessage(
                        conversation_id=convo.id, organization_id=org_a, brand_id=brand_a,
                        role=role, content=body, seq=i,
                    )
                )
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            msgs = await service.list_messages(s, tenant=t_a, conversation_id=convo_id)
            assert [m.seq for m in msgs] == [1, 2, 3]  # ordered
            assert [m.role for m in msgs] == ["user", "assistant", "user"]
            convos = await service.list_conversations(s, tenant=t_a)
            assert any(c.id == convo_id for c in convos)

        # cross-tenant: brand B cannot see brand A's conversation (404, not 403)
        async with AsyncSession(eng, expire_on_commit=False) as s:
            with pytest.raises(HTTPException) as exc:
                await service.get_conversation(s, tenant=t_b, conversation_id=convo_id)
            assert exc.value.status_code == 404
            with pytest.raises(HTTPException):
                await service.list_messages(s, tenant=t_b, conversation_id=convo_id)
            # B's own list does not include A's conversation
            assert all(c.id != convo_id for c in await service.list_conversations(s, tenant=t_b))
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM agent_messages WHERE organization_id IN (:a,:b)"), {"a": org_a, "b": org_b})
            await conn.execute(text("DELETE FROM agent_conversations WHERE organization_id IN (:a,:b)"), {"a": org_a, "b": org_b})
            await conn.execute(text("DELETE FROM brands WHERE organization_id IN (:a,:b)"), {"a": org_a, "b": org_b})
            await conn.execute(text("DELETE FROM organizations WHERE id IN (:a,:b)"), {"a": org_a, "b": org_b})
            await conn.execute(text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": user_a, "b": user_b})
        await eng.dispose()
