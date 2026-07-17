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
    # Extra dedupe discriminator for sources without a row id (e.g. a decision).
    dedupe_hint: str | None = None
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
    return await persist_drafts(
        session, organization_id=organization_id, brand_id=brand_id, drafts=drafts
    )


async def persist_drafts(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    drafts: list[WorkDraft],
) -> int:
    """Policy-gate + persist a list of WorkDrafts, deduped against open items.
    Shared by the deterministic scheduler (events/goals) and the decision
    pipeline (4.6). Does not commit."""
    if not drafts:
        return 0

    from aicmo.config import get_settings
    from aicmo.modules.autonomy import service as autonomy_service

    settings = get_settings()
    config = await autonomy_service.get_or_default(session, brand_id=brand_id)
    exec_enabled = settings.autonomy_execution_enabled

    # Guardrail (Phase 8, Priority 3): never queue more than the owner's
    # max-tasks-per-cycle ceiling. Highest priority first so the most valuable
    # work survives the cap; the rest is held for the next cycle and the owner
    # is told what's waiting.
    max_tasks = settings.operations_max_tasks_per_cycle
    _rank = {"high": 0, "medium": 1, "low": 2}
    drafts = sorted(drafts, key=lambda d: _rank.get(d.priority, 3))
    held_back = 0
    if max_tasks >= 0 and len(drafts) > max_tasks:
        held_back = len(drafts) - max_tasks
        drafts = drafts[:max_tasks]

    existing = await _open_dedupe_keys(session, brand_id=brand_id)
    created = 0
    for d in drafts:
        disc = d.source_id or d.dedupe_hint or d.source_kind
        dedupe = f"{brand_id}:{d.kind}:{disc}"
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

    # Told-you-what-remains: when the cap held work back, leave the owner a
    # plain-language note rather than silently dropping it. `_emit` is sync,
    # dedupes on the day so we don't repeat it, and falls back to a valid
    # category on its own.
    if held_back > 0:
        try:
            from aicmo.modules.operations import notifier

            note_now = datetime.now(UTC)
            day = note_now.date().isoformat()
            notifier._emit(
                session,
                organization_id=organization_id,
                brand_id=brand_id,
                category="operations",
                kind="work_deferred",
                title="A few more ideas are waiting for tomorrow",
                body=(
                    f"I prepared the {created} most important thing"
                    f"{'' if created == 1 else 's'} for you today and saved "
                    f"{held_back} more idea{'' if held_back == 1 else 's'} for "
                    "the next round, so I don't overwhelm you."
                ),
                severity="info",
                link="/ai-employee",
                dedupe_key=f"{brand_id}:work_deferred:{day}",
                now=note_now,
            )
        except Exception as e:
            log.warning("ops.scheduler.defer_note_failed", error=str(e)[:120])

    return created
