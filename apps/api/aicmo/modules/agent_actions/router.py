"""Approval-gated consequential-action API (Phase 4A).

Authenticated + tenant-scoped. Tenant/user are ALWAYS derived server-side via
``require_tenant`` / ``require_permission`` — never from the request body.

    POST /api/v1/agent/actions/propose        propose (creates PENDING; never runs)
    GET  /api/v1/agent/actions                list this tenant's approvals
    GET  /api/v1/agent/actions/{id}           read one
    POST /api/v1/agent/actions/{id}/approve   human approval (settings.manage)
    POST /api/v1/agent/actions/{id}/reject    human rejection (settings.manage)
    POST /api/v1/agent/actions/{id}/execute   run the EXACT approved action

Proposing requires the same publishing permission the underlying action needs;
approving / rejecting / executing require the privileged ``settings.manage``
authority (the same release authority the operations loop uses).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.agent_actions import service
from aicmo.modules.agent_actions.schemas import (
    ApprovalListResponse,
    ApprovalView,
    DecisionRequest,
    ProposeActionRequest,
    ProposeActionResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

router = APIRouter(prefix="/api/v1/agent/actions", tags=["agent-actions"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("/propose", response_model=ProposeActionResponse, status_code=201)
async def propose_action(
    payload: ProposeActionRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> ProposeActionResponse:
    try:
        row = await service.propose_action(
            session, tenant=tenant, request=payload, request_id=_request_id(request)
        )
    except service.ActionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await session.commit()
    return ProposeActionResponse(
        approval=service._view(row),
        approval_required=True,
        executed=False,
        message="A human must approve this action before it can run. Nothing has executed.",
    )


@router.get("", response_model=ApprovalListResponse)
async def list_actions(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> ApprovalListResponse:
    rows = await service.list_approvals(session, tenant=tenant, status=status_filter)
    await session.commit()
    return ApprovalListResponse(items=[service._view(r) for r in rows])


@router.get("/{approval_id}", response_model=ApprovalView)
async def get_action(
    approval_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> ApprovalView:
    try:
        row = await service.get_approval(session, tenant=tenant, approval_id=approval_id)
    except service.ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.") from exc
    await session.commit()
    return service._view(row)


@router.post("/{approval_id}/approve", response_model=ApprovalView)
async def approve_action(
    approval_id: uuid.UUID,
    payload: DecisionRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> ApprovalView:
    row = await _decide(session, tenant=tenant, approval_id=approval_id, approve=True, reason=payload.reason)
    await session.commit()
    return service._view(row)


@router.post("/{approval_id}/reject", response_model=ApprovalView)
async def reject_action(
    approval_id: uuid.UUID,
    payload: DecisionRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> ApprovalView:
    row = await _decide(session, tenant=tenant, approval_id=approval_id, approve=False, reason=payload.reason)
    await session.commit()
    return service._view(row)


@router.post("/{approval_id}/execute", response_model=ApprovalView)
async def execute_action(
    approval_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> ApprovalView:
    try:
        row = await service.execute_approved(
            session, tenant=tenant, approval_id=approval_id, request_id=_request_id(request)
        )
    except service.ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.") from exc
    except service.ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return service._view(row)


async def _decide(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    approval_id: uuid.UUID,
    approve: bool,
    reason: str | None,
):
    try:
        if approve:
            return await service.approve(session, tenant=tenant, approval_id=approval_id, reason=reason)
        return await service.reject(session, tenant=tenant, approval_id=approval_id, reason=reason)
    except service.ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.") from exc
    except service.ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
