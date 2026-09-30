"""Conversation persistence — tenant/brand scoped, read-mostly.

Every query filters by the caller's brand_id + organization_id (from the trusted
TenantContext); a conversation is never loaded across brands. This is the
service-layer half of tenant isolation; the org-scoped RLS policy is the
defense-in-depth half.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.agent.models import AgentConversation, AgentMessage
from aicmo.tenancy.context import TenantContext

_LIST_LIMIT = 50


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A brand must be selected.")
    return tenant.brand_id


async def create_conversation(
    session: AsyncSession, *, tenant: TenantContext, title: str | None
) -> AgentConversation:
    brand_id = _require_brand(tenant)
    convo = AgentConversation(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        user_id=tenant.user_uuid,
        title=title,
        status="active",
    )
    session.add(convo)
    await session.flush()
    return convo


async def get_conversation(
    session: AsyncSession, *, tenant: TenantContext, conversation_id: uuid.UUID
) -> AgentConversation:
    brand_id = _require_brand(tenant)
    convo = (
        await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.brand_id == brand_id,
                AgentConversation.organization_id == tenant.organization_id,
            )
        )
    ).scalar_one_or_none()
    if convo is None:
        # 404 (not 403) so existence never leaks across tenants.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return convo


async def list_conversations(
    session: AsyncSession, *, tenant: TenantContext
) -> list[AgentConversation]:
    brand_id = _require_brand(tenant)
    rows = (
        (
            await session.execute(
                select(AgentConversation)
                .where(
                    AgentConversation.brand_id == brand_id,
                    AgentConversation.organization_id == tenant.organization_id,
                )
                .order_by(desc(AgentConversation.updated_at))
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_messages(
    session: AsyncSession, *, tenant: TenantContext, conversation_id: uuid.UUID
) -> list[AgentMessage]:
    # Re-validates ownership (raises 404 across tenants) before returning rows.
    await get_conversation(session, tenant=tenant, conversation_id=conversation_id)
    rows = (
        (
            await session.execute(
                select(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
                .order_by(AgentMessage.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
