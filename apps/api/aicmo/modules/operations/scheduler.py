"""Phase 4.4 — Autonomous Work Scheduler.

Deterministically proposes marketing WORK from open events + goal gaps, then
gates every item through the Autonomy Policy (Module 9/10). Nothing executes:
by default the master switch is OFF and the policy requires approval, so items
land as `awaiting_approval`. Grounded entirely in real events/goals — no
fabricated work.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations.models import (
    DetectedEvent,
    OperationalGoal,
    ScheduledWork,
)

log = structlog.get_logger()


@dataclass
class WorkDraft:
    kind: str
    action_type: str
    title: str
    description: str
    rationale: str
    priority: str = "medium"
    source_kind: str = "event"
    source_id: uuid.UUID | None = None
    tags: list[str] = field(default_factory=list)


# event_type → the work it should trigger. Kept a table so it's obvious + testable.
_EVENT_WORK: dict[str, tuple[str, str, str, str]] = {
    # event_type: (kind, action_type, priority, title)
    "no_recent_leads": ("content_generation", "content_generation", "high",
                        "Generate lead-focused content to restart the pipeline"),
    "leads_declining": ("content_generation", "content_generation", "high",
                        "Generate lead-focused content to reverse the decline"),
    "conversion_drop": ("campaign_update", "campaign_creation", "high",
                        "Improve the landing page / offer to lift conversion"),
    "traffic_drop": ("content_generation", "content_generation", "medium",
                    "Publish fresh content to recover traffic"),
    "traffic_spike": ("content_generation", "content_generation", "medium",
                    "Publish a timely post to capitalise on the traffic spike"),
    "leads_surge": ("campaign_update", "campaign_creation", "medium",
                    "Double down on what's driving the lead surge"),
    "publishing_failures": ("campaign_update", "social_publishing", "high",
                            "Review and retry the posts that failed to publish"),
    "performance_flagged": ("ad", "ad_creation", "medium",
                            "Review the newly flagged performance issues"),
}


def propose_from_events(events: list[DetectedEvent]) -> list[WorkDraft]:
    drafts: list[WorkDraft] = []
    for ev in events:
        spec = _EVENT_WORK.get(ev.event_type)
        if spec is None:
            continue
        kind, action_type, priority, title = spec
        drafts.append(WorkDraft(
            kind=kind, action_type=action_type, title=title,
            description=title,
            rationale=f"Triggered by detected event: {ev.title} — {ev.summary}",
            priority=priority, source_kind="event", source_id=ev.id,
        ))
    return drafts


def propose_from_goals(goals: list[OperationalGoal]) -> list[WorkDraft]:
    """For measurable, active goals that are under-progressed, schedule work to
    advance them. Deterministic: <50% progress on an increase/reach goal."""
    from aicmo.modules.operations.goals import progress_fraction

    drafts: list[WorkDraft] = []
    for g in goals:
        if not g.measurable or g.status != "active":
            continue
        frac = progress_fraction(g)
        if frac is None or frac >= 0.5:
            continue
        drafts.append(WorkDraft(
            kind="content_generation", action_type="content_generation",
            title=f"Advance your goal: {g.title}",
            description=f"Create marketing work to move '{g.metric}' toward {g.target_value:g}.",
            rationale=f"Goal '{g.title}' is only {frac * 100:.0f}% there (now {g.current_value:g}).",
            priority="medium", source_kind="goal", source_id=g.id,
        ))
    return drafts


async def _open_dedupe_keys(session: AsyncSession, *, brand_id: uuid.UUID) -> set[str]:
    stmt = select(ScheduledWork.dedupe_key).where(
        ScheduledWork.brand_id == brand_id,
        ScheduledWork.status.in_(
            ("proposed", "awaiting_approval", "approved", "queued")
        ),
    )
    return {row[0] for row in (await session.execute(stmt)).all()}


async def _weekly_report_due(
    session: AsyncSession, *, brand_id: uuid.UUID, now: datetime
) -> bool:
    stmt = (
        select(ScheduledWork.created_at)
        .where(
            ScheduledWork.brand_id == brand_id,
            ScheduledWork.kind == "weekly_report",
        )
        .order_by(desc(ScheduledWork.created_at))
        .limit(1)
    )
    last = (await session.execute(stmt)).scalar_one_or_none()
    return last is None or last < now - timedelta(days=7)


async def schedule_work(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Propose + persist policy-gated work for one brand. Deduped against open
    items. Does not commit. Returns the number of new work items."""
    now = now or datetime.now(UTC)

    # Sources: open events + active goals (+ recurring weekly report).
    ev_rows = list((await session.execute(
        select(DetectedEvent).where(
            DetectedEvent.brand_id == brand_id,
            DetectedEvent.status.in_(("new", "acknowledged")),
        )
    )).scalars().all())
    goal_rows = list((await session.execute(
        select(OperationalGoal).where(
            OperationalGoal.brand_id == brand_id,
            OperationalGoal.status == "active",
        )
    )).scalars().all())

    drafts = propose_from_events(ev_rows) + propose_from_goals(goal_rows)
    if await _weekly_report_due(session, brand_id=brand_id, now=now):
        drafts.append(WorkDraft(
            kind="weekly_report", action_type="ai_recommendation",
            title="Create this week's performance report",
            description="Summarise the week's results, wins, and next moves.",
            rationale="Recurring weekly cadence — keep the owner informed.",
            priority="low", source_kind="recurring",
        ))

    if not drafts:
        return 0

    # Evaluate the Autonomy Policy once per brand.
    from aicmo.config import get_settings
    from aicmo.modules.autonomy import service as autonomy_service

    config = await autonomy_service.get_or_default(session, brand_id=brand_id)
    exec_enabled = get_settings().autonomy_execution_enabled

    existing = await _open_dedupe_keys(session, brand_id=brand_id)
    created = 0
    for d in drafts:
        dedupe = f"{brand_id}:{d.kind}:{d.source_id or d.source_kind}"
        if dedupe in existing:
            continue
        decision = autonomy_service.evaluate_policy(
            config, d.action_type, execution_enabled=exec_enabled
        )
        session.add(ScheduledWork(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_id=brand_id,
            kind=d.kind,
            action_type=d.action_type,
            title=d.title,
            description=d.description,
            rationale=d.rationale,
            source_kind=d.source_kind,
            source_id=d.source_id,
            priority=d.priority,
            requires_approval=decision.requires_approval,
            auto_eligible=decision.allow_auto,
            policy_mode=decision.mode,
            # Safe default: even auto-eligible work only 'queues' — real
            # execution wiring is a later, still-gated step (4.9 keeps it off).
            status="queued" if decision.allow_auto else "awaiting_approval",
            dedupe_key=dedupe,
        ))
        existing.add(dedupe)
        created += 1
    return created
