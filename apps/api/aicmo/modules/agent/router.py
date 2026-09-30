"""Read-only agent API.

Authenticated + tenant-scoped (require_tenant → first-party session, no anonymous
access, no demo bypass). Rate limiting, request-id, and security headers come
from the existing global middleware. The turn itself executes only READ tools.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.agent import service
from aicmo.modules.agent.runtime import run_turn
from aicmo.modules.agent.schemas import (
    AgentResponse,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageRequest,
    MessageResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_tenant

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _convo_out(convo) -> ConversationResponse:
    return ConversationResponse(
        id=convo.id,
        title=convo.title,
        status=convo.status,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
    )


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    payload: ConversationCreateRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> ConversationResponse:
    convo = await service.create_conversation(session, tenant=tenant, title=payload.title)
    await session.commit()
    return _convo_out(convo)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> ConversationListResponse:
    rows = await service.list_conversations(session, tenant=tenant)
    return ConversationListResponse(items=[_convo_out(c) for c in rows])


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> MessageListResponse:
    rows = await service.list_messages(session, tenant=tenant, conversation_id=conversation_id)
    return MessageListResponse(
        conversation_id=conversation_id,
        items=[
            MessageResponse.model_validate(
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "seq": m.seq,
                    "created_at": m.created_at,
                    "meta": m.meta,
                }
            )
            for m in rows
        ],
    )


@router.post("/conversations/{conversation_id}/messages", response_model=AgentResponse)
async def post_message(
    conversation_id: uuid.UUID,
    payload: MessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> AgentResponse:
    convo = await service.get_conversation(session, tenant=tenant, conversation_id=conversation_id)
    request_id = getattr(request.state, "request_id", None)
    response = await run_turn(
        session,
        tenant=tenant,
        conversation=convo,
        user_text=payload.content,
        request_id=request_id,
    )
    await session.commit()
    return response
