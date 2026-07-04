"""CRM Tasks & Calendar HTTP API (Phase 6.5, Slice 3). Mounted under /crm.
Tenant-scoped + RBAC (crm.view / crm.manage) + audited + ownership-validated."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.crm import tasks_service as svc
from aicmo.modules.crm.tasks_schemas import (
    TaskCompleteRequest,
    TaskCreate,
    TaskList,
    TaskResponse,
    TaskUpdate,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm", tags=["crm-tasks"])

_VIEW = require_permission("crm.view")
_MANAGE = require_permission("crm.manage")


async def _list(session, tenant, **kw) -> TaskList:
    rows, total = await svc.list_tasks(session, tenant=tenant, **kw)
    return TaskList(items=[TaskResponse.model_validate(t) for t in rows], total=total)


@router.get("/tasks", response_model=TaskList)
async def list_tasks(
    queue: str | None = Query(default=None, description="today|upcoming|overdue|completed|mine"),
    status: str | None = Query(default=None),
    assignee_user_id: str | None = Query(default=None),
    activity_type: str | None = Query(default=None),
    deal_id: uuid.UUID | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    company_id: uuid.UUID | None = Query(default=None),
    lead_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> TaskList:
    return await _list(
        session, tenant, queue=queue, task_status=status, assignee_user_id=assignee_user_id,
        activity_type=activity_type, deal_id=deal_id, contact_id=contact_id,
        company_id=company_id, lead_id=lead_id, q=q, limit=limit, offset=offset,
    )


@router.get("/calendar", response_model=TaskList)
async def calendar(
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> TaskList:
    """Tasks with a due date in [start, end] — the source for day/week/month/
    agenda views (rendered client-side)."""
    return await _list(session, tenant, start=start, end=end, limit=200)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> TaskResponse:
    return TaskResponse.model_validate(await svc.create_task(session, tenant=tenant, payload=payload))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> TaskResponse:
    return TaskResponse.model_validate(await svc.get_task(session, tenant=tenant, task_id=task_id))


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> TaskResponse:
    return TaskResponse.model_validate(
        await svc.update_task(session, tenant=tenant, task_id=task_id, payload=payload)
    )


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> None:
    await svc.delete_task(session, tenant=tenant, task_id=task_id)


@router.post("/tasks/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: uuid.UUID, payload: TaskCompleteRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> TaskResponse:
    return TaskResponse.model_validate(
        await svc.complete_task(
            session, tenant=tenant, task_id=task_id,
            actual_minutes=payload.actual_minutes, notes=payload.notes,
        )
    )


@router.post("/tasks/{task_id}/suggest", response_model=TaskResponse)
async def suggest_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> TaskResponse:
    """Grounded AI suggestion (priority / due / next step / risk) — cached on the task."""
    return TaskResponse.model_validate(
        await svc.generate_suggestion(session, tenant=tenant, task_id=task_id)
    )
