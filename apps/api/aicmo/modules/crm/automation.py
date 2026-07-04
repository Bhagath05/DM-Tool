"""CRM task automation (Phase 6.5, Slice 3).

Auto-drafts a follow-up task on real CRM events (deal moved / won / lost,
contact created, meeting completed). Titles are GROUNDED in the real record —
never fabricated. Every generator only STAGES the task (via tasks_service.
stage_task, no commit) so it lands atomically inside the parent op's
transaction, and is wrapped best-effort so automation can never break the
parent operation.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.crm import tasks_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


def _followup(
    session: AsyncSession, *, tenant: TenantContext, title: str, event: str,
    activity_type: str = "follow_up", due_in_days: int = 2, priority: str = "medium", **links,
) -> None:
    with contextlib.suppress(Exception):  # automation must never break the parent op
        tasks_service.stage_task(
            session, tenant=tenant, title=title[:240], activity_type=activity_type,
            priority=priority, due_at=datetime.now(UTC) + timedelta(days=due_in_days),
            source=f"automation:{event}", **links,
        )
        log.info("crm.automation.task", event=event)


def on_deal_moved(session, *, tenant, deal, stage_name: str) -> None:
    _followup(
        session, tenant=tenant, event="deal_moved",
        title=f"Next step on '{deal.title}' — now in {stage_name}",
        deal_id=deal.id, company_id=deal.company_id, contact_id=deal.primary_contact_id,
    )


def on_deal_won(session, *, tenant, deal) -> None:
    _followup(
        session, tenant=tenant, event="deal_won", activity_type="follow_up", priority="high",
        due_in_days=1, title=f"Kick off onboarding for won deal '{deal.title}'",
        deal_id=deal.id, company_id=deal.company_id, contact_id=deal.primary_contact_id,
    )


def on_deal_lost(session, *, tenant, deal) -> None:
    _followup(
        session, tenant=tenant, event="deal_lost", activity_type="internal", due_in_days=3,
        title=f"Log loss reason + nurture plan for '{deal.title}'",
        deal_id=deal.id, company_id=deal.company_id,
    )


def on_contact_created(session, *, tenant, contact) -> None:
    _followup(
        session, tenant=tenant, event="contact_created", due_in_days=2,
        title=f"Introductory outreach to {contact.name}",
        contact_id=contact.id, company_id=contact.company_id,
    )


def on_meeting_completed(session, *, tenant, task) -> None:
    _followup(
        session, tenant=tenant, event="meeting_completed", due_in_days=1, priority="high",
        title=f"Send follow-up after: {task.title}",
        deal_id=task.deal_id, contact_id=task.contact_id, company_id=task.company_id,
        lead_id=task.lead_id,
    )


def on_lead_assigned(session, *, tenant, lead, title: str | None = None) -> None:
    """Exposed for when the leads module gains an assignment event; not
    auto-wired today (leads have no owner/assignee field yet)."""
    _followup(
        session, tenant=tenant, event="lead_assigned", due_in_days=1,
        title=title or f"Qualify new lead {getattr(lead, 'name', '') or lead.email}",
        lead_id=lead.id,
    )
