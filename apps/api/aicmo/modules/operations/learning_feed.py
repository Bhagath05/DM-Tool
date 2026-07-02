"""Phase 4.5 — Memory & Learning Expansion.

Audited first: the Learning Engine (Module 6) ALREADY stores winning creatives /
hooks / posting-times (LearningEvent + social WinningPattern/AudiencePattern),
winning & failed strategies (LearningInsight categories), and owner
approvals/outcomes (advisor memory). Rebuilding any of that would duplicate
working code.

What was missing: the CONTINUOUS LOOP's own real execution signals — what work
the owner actually approved vs dismissed, which events keep recurring, and which
goals were actually hit. This module summarises those (from real rows only,
never invented) so the existing synthesis can learn from the autonomous loop's
activity. Dependency-light: imports ONLY operations models.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations.models import (
    DetectedEvent,
    OperationalGoal,
    ScheduledWork,
)


async def learning_signals(
    session: AsyncSession, *, brand_id: uuid.UUID, days: int = 60
) -> list[str]:
    """Plain-language lines summarising the loop's real execution history for
    this brand. Empty when there's nothing real to report — never fabricated."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    lines: list[str] = []

    # Approval history — what the owner approved vs dismissed (a preference signal).
    work_rows = list((await session.execute(
        select(ScheduledWork.kind, ScheduledWork.status).where(
            ScheduledWork.brand_id == brand_id,
            ScheduledWork.created_at >= cutoff,
        )
    )).all())
    approved = Counter(k for k, s in work_rows if s in ("approved", "queued", "executed"))
    dismissed = Counter(k for k, s in work_rows if s == "dismissed")
    if approved:
        top = ", ".join(f"{k} x{n}" for k, n in approved.most_common(4))
        lines.append(f"Owner APPROVED work: {top}.")
    if dismissed:
        top = ", ".join(f"{k} x{n}" for k, n in dismissed.most_common(4))
        lines.append(f"Owner DISMISSED work (avoid proposing these): {top}.")

    # Recurring events — a persistent condition worth a durable lesson.
    ev_rows = list((await session.execute(
        select(DetectedEvent.event_type).where(
            DetectedEvent.brand_id == brand_id,
            DetectedEvent.detected_at >= cutoff,
        )
    )).all())
    ev_counts = Counter(t for (t,) in ev_rows)
    recurring = [(t, n) for t, n in ev_counts.items() if n >= 2]
    if recurring:
        top = ", ".join(f"{t} x{n}" for t, n in sorted(recurring, key=lambda x: -x[1])[:4])
        lines.append(f"Recurring detected events: {top}.")

    # Goal outcomes — actually achieved (a success to reinforce).
    goal_rows = list((await session.execute(
        select(OperationalGoal.title, OperationalGoal.status).where(
            OperationalGoal.brand_id == brand_id,
        )
    )).all())
    achieved = [t for t, s in goal_rows if s == "achieved"]
    if achieved:
        lines.append("Goals achieved: " + "; ".join(achieved[:4]) + ".")

    return lines
