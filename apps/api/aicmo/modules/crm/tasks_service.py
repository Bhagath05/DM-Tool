"""CRM Tasks & Calendar service (Phase 6.5, Slice 3).

Full task management over the CRM graph: CRUD, recurrence (next occurrence
generated on completion), the queues (today / upcoming / overdue / completed /
mine / team), and a calendar range query. All brand-scoped, ownership-validated,
and audited. `stage_task` builds a task WITHOUT committing so the automation
hooks can attach a follow-up inside the parent op's transaction (atomic).
"""

from __future__ import annotations

import calendar as _cal
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.campaigns.models import CampaignPlan
from aicmo.modules.crm._shared import record_crm_audit as _audit
from aicmo.modules.crm.models import Company, Contact, Deal, Task
from aicmo.modules.crm.tasks_schemas import TaskCreate, TaskUpdate
from aicmo.modules.leads.models import Lead
from aicmo.tenancy.context import TenantContext

_TERMINAL = ("completed", "cancelled")




async def _validate_links(session: AsyncSession, *, tenant: TenantContext, links: dict) -> None:
    """Every linked record must belong to the caller's brand (tenant safety)."""
    checks = [
        ("lead_id", Lead), ("contact_id", Contact), ("company_id", Company),
        ("deal_id", Deal), ("campaign_id", CampaignPlan),
    ]
    for field, model in checks:
        rid = links.get(field)
        if rid is None:
            continue
        row = await session.get(model, rid)
        if row is None or row.brand_id != tenant.brand_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Linked {field[:-3]} not found.")


def add_months(dt: datetime, months: int) -> datetime:
    """Add whole months, clamping the day to the target month's length."""
    m = dt.month - 1 + months
    year = dt.year + m // 12
    month = m % 12 + 1
    day = min(dt.day, _cal.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def next_due(due_at: datetime, recurrence: dict) -> datetime:
    freq = recurrence.get("freq")
    interval = int(recurrence.get("interval", 1) or 1)
    if freq == "daily":
        return due_at + timedelta(days=interval)
    if freq == "weekly":
        return due_at + timedelta(weeks=interval)
    if freq == "monthly":
        return add_months(due_at, interval)
    return due_at + timedelta(days=interval)


def stage_task(
    session: AsyncSession, *, tenant: TenantContext, title: str,
    activity_type: str = "follow_up", priority: str = "medium",
    due_at: datetime | None = None, source: str = "manual", **fields,
) -> Task:
    """Build + add a task WITHOUT committing (caller's transaction persists it)."""
    row = Task(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        title=title, activity_type=activity_type, priority=priority, due_at=due_at,
        owner_user_id=fields.pop("owner_user_id", None) or tenant.user_id,
        assignee_user_id=fields.pop("assignee_user_id", None) or tenant.user_id,
        created_by_user_id=tenant.user_id, source=source, **fields,
    )
    session.add(row)
    return row


async def create_task(session: AsyncSession, *, tenant: TenantContext, payload: TaskCreate) -> Task:
    links = payload.model_dump(include={"lead_id", "contact_id", "company_id", "deal_id", "campaign_id"})
    await _validate_links(session, tenant=tenant, links=links)
    rec = payload.recurrence.model_dump(mode="json") if payload.recurrence else None
    row = stage_task(
        session, tenant=tenant, title=payload.title, activity_type=payload.activity_type,
        priority=payload.priority, due_at=payload.due_at, source="manual",
        description=payload.description, owner_user_id=payload.owner_user_id,
        assignee_user_id=payload.assignee_user_id, reminder_at=payload.reminder_at,
        is_recurring=rec is not None, recurrence=rec, calendar_event=payload.calendar_event,
        estimated_minutes=payload.estimated_minutes, notes=payload.notes,
        attachments=payload.attachments, tags=payload.tags, **links,
    )
    await _audit(session, tenant=tenant, action="crm.task_created", target_id=row.id,
                 metadata={"title": payload.title, "activity_type": payload.activity_type})
    await session.commit()
    await session.refresh(row)
    return row


async def _owned_task(session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID) -> Task:
    row = await session.get(Task, task_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    return row


async def get_task(session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID) -> Task:
    return await _owned_task(session, tenant=tenant, task_id=task_id)


async def list_tasks(
    session: AsyncSession, *, tenant: TenantContext, queue: str | None = None,
    task_status: str | None = None, assignee_user_id: str | None = None,
    activity_type: str | None = None, deal_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None, company_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None, q: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    limit: int = 100, offset: int = 0,
) -> tuple[list[Task], int]:
    now = datetime.now(UTC)
    conds = [Task.brand_id == tenant.brand_id]

    # Queues are derived filters (never a separate table).
    if queue == "today":
        day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        conds += [Task.status.notin_(_TERMINAL), Task.due_at.isnot(None), Task.due_at <= day_end]
    elif queue == "upcoming":
        conds += [Task.status.notin_(_TERMINAL), Task.due_at.isnot(None), Task.due_at > now]
    elif queue == "overdue":
        conds += [Task.status.notin_(_TERMINAL), Task.due_at.isnot(None), Task.due_at < now]
    elif queue == "completed":
        conds.append(Task.status == "completed")
    elif queue == "mine":
        conds += [Task.status.notin_(_TERMINAL), Task.assignee_user_id == tenant.user_id]

    if task_status is not None:
        conds.append(Task.status == task_status)
    if assignee_user_id is not None:
        conds.append(Task.assignee_user_id == assignee_user_id)
    if activity_type is not None:
        conds.append(Task.activity_type == activity_type)
    for field, val in (("deal_id", deal_id), ("contact_id", contact_id),
                       ("company_id", company_id), ("lead_id", lead_id)):
        if val is not None:
            conds.append(getattr(Task, field) == val)
    if start is not None:
        conds.append(Task.due_at >= start)
    if end is not None:
        conds.append(Task.due_at <= end)
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Task.title.ilike(like), Task.description.ilike(like)))

    total = (await session.execute(select(func.count()).select_from(Task).where(*conds))).scalar_one()
    # Overdue/soonest first for active queues; newest for completed.
    order = Task.completed_at.desc() if queue == "completed" else Task.due_at.asc().nulls_last()
    rows = await session.execute(
        select(Task).where(*conds).order_by(order, Task.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def update_task(session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID, payload: TaskUpdate) -> Task:
    row = await _owned_task(session, tenant=tenant, task_id=task_id)
    data = payload.model_dump(exclude_unset=True)
    link_fields = {k: data[k] for k in ("lead_id", "contact_id", "company_id", "deal_id", "campaign_id") if k in data}
    if link_fields:
        await _validate_links(session, tenant=tenant, links=link_fields)
    if data.get("status") == "completed" and row.completed_at is None:
        row.completed_at = datetime.now(UTC)
    for k, v in data.items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


async def complete_task(
    session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID,
    actual_minutes: int | None = None, notes: str | None = None,
) -> Task:
    row = await _owned_task(session, tenant=tenant, task_id=task_id)
    now = datetime.now(UTC)
    row.status = "completed"
    row.completed_at = now
    if actual_minutes is not None:
        row.actual_minutes = actual_minutes
    if notes:
        row.notes = (row.notes + "\n" if row.notes else "") + notes

    # Recurring → spawn the next occurrence (respecting until / count limits).
    if row.is_recurring and row.recurrence and row.due_at is not None:
        rec = dict(row.recurrence)
        remaining = rec.get("count")
        due = next_due(row.due_at, rec)
        until = rec.get("until")
        stop = (remaining is not None and remaining <= 1) or (
            until is not None and due > datetime.fromisoformat(until)
        )
        if not stop:
            if remaining is not None:
                rec["count"] = remaining - 1
            stage_task(
                session, tenant=tenant, title=row.title, activity_type=row.activity_type,
                priority=row.priority, due_at=due, source="recurrence",
                description=row.description, assignee_user_id=row.assignee_user_id,
                owner_user_id=row.owner_user_id, is_recurring=True, recurrence=rec,
                recurrence_parent_id=row.recurrence_parent_id or row.id,
                calendar_event=row.calendar_event, estimated_minutes=row.estimated_minutes,
                tags=row.tags, lead_id=row.lead_id, contact_id=row.contact_id,
                company_id=row.company_id, deal_id=row.deal_id, campaign_id=row.campaign_id,
            )

    # Completing a meeting auto-drafts a follow-up (automation, best-effort).
    if row.activity_type in ("meeting", "demo", "call"):
        from aicmo.modules.crm import automation
        automation.on_meeting_completed(session, tenant=tenant, task=row)

    await _audit(session, tenant=tenant, action="crm.task_completed", target_id=row.id, metadata={})
    await session.commit()
    await session.refresh(row)
    return row


async def delete_task(session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID) -> None:
    row = await _owned_task(session, tenant=tenant, task_id=task_id)
    await session.delete(row)
    await session.commit()


async def generate_suggestion(session: AsyncSession, *, tenant: TenantContext, task_id: uuid.UUID) -> Task:
    from aicmo.modules.crm import ai

    row = await _owned_task(session, tenant=tenant, task_id=task_id)
    suggestion = await ai.task_suggestion(session, row)
    row.ai_suggestion = suggestion.model_dump()
    row.ai_generated_at = datetime.now(UTC)
    await _audit(session, tenant=tenant, action="crm.task_suggestion", target_id=row.id,
                 metadata={"confidence": suggestion.confidence})
    await session.commit()
    await session.refresh(row)
    return row
