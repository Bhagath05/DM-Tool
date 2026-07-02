"""Phase 4.3 — Autonomous Goal Engine.

Users define goals; the operations cycle measures progress from REAL metric
snapshots (deterministic, no invented numbers); active goals feed Strategy,
Planner, and the Decision Engine via `active_goals_context`.

Goals whose metric isn't captured yet (roas / cpa / followers / appointments)
are tracked honestly as `measurable=False` — no fabricated progress.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations.models import OperationalGoal

log = structlog.get_logger()

# Goal metric → the snapshot metric key that measures it. None = not yet
# captured by monitoring (tracked, but progress is honestly "unmeasured").
_METRIC_MAP: dict[str, str | None] = {
    "leads": "total_leads",
    "website_traffic": "total_views",
    "conversions": "conversion_rate",
    "content_output": "published_posts",
    "roas": None,
    "cpa": None,
    "instagram_followers": None,
    "linkedin_followers": None,
    "appointments": None,
}


def snapshot_key_for(metric: str) -> str | None:
    return _METRIC_MAP.get(metric)


def is_measurable(metric: str) -> bool:
    return _METRIC_MAP.get(metric) is not None


def progress_fraction(goal: OperationalGoal) -> float | None:
    """0..1 progress toward target, or None when it can't be computed. Pure."""
    if not goal.measurable:
        return None
    base, cur, tgt = goal.baseline_value, goal.current_value, goal.target_value
    if goal.goal_type == "reach":
        return None if tgt == 0 else max(0.0, min(1.0, cur / tgt))
    if goal.goal_type == "decrease":
        denom = base - tgt
        return max(0.0, min(1.0, (base - cur) / denom)) if denom else None
    # increase (default)
    denom = tgt - base
    return max(0.0, min(1.0, (cur - base) / denom)) if denom else None


def is_achieved(goal: OperationalGoal) -> bool:
    if not goal.measurable:
        return False
    if goal.goal_type == "decrease":
        return goal.current_value <= goal.target_value
    return goal.current_value >= goal.target_value


def to_response(goal: OperationalGoal):
    """ORM → GoalResponse with the derived progress_pct."""
    from aicmo.modules.operations.schemas import GoalResponse

    frac = progress_fraction(goal)
    resp = GoalResponse.model_validate(goal)
    resp.progress_pct = round(frac * 100) if frac is not None else None
    return resp


# ---------------------------------------------------------------------
#  CRUD
# ---------------------------------------------------------------------
async def list_goals(
    session: AsyncSession, *, brand_id: uuid.UUID, only_active: bool = False
) -> list[OperationalGoal]:
    stmt = select(OperationalGoal).where(OperationalGoal.brand_id == brand_id)
    if only_active:
        stmt = stmt.where(OperationalGoal.status == "active")
    stmt = stmt.order_by(desc(OperationalGoal.created_at)).limit(100)
    return list((await session.execute(stmt)).scalars().all())


async def create_goal(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    user_id: str,
    title: str,
    metric: str,
    goal_type: str,
    target_value: float,
    timeframe_days: int | None,
    baseline_value: float = 0.0,
) -> OperationalGoal:
    measurable = is_measurable(metric)
    row = OperationalGoal(
        id=uuid.uuid4(),
        organization_id=organization_id,
        brand_id=brand_id,
        user_id=user_id,
        title=title,
        metric=metric,
        goal_type=goal_type,
        target_value=target_value,
        baseline_value=baseline_value if measurable else 0.0,
        current_value=baseline_value if measurable else 0.0,
        timeframe_days=timeframe_days,
        measurable=measurable,
        status="active",
    )
    session.add(row)
    await session.flush()
    return row


async def get_goal(
    session: AsyncSession, *, brand_id: uuid.UUID, goal_id: uuid.UUID
) -> OperationalGoal | None:
    row = await session.get(OperationalGoal, goal_id)
    if row is None or row.brand_id != brand_id:
        return None
    return row


async def set_status(
    session: AsyncSession, *, brand_id: uuid.UUID, goal_id: uuid.UUID, status: str
) -> OperationalGoal | None:
    row = await get_goal(session, brand_id=brand_id, goal_id=goal_id)
    if row is None:
        return None
    row.status = status
    await session.flush()
    return row


# ---------------------------------------------------------------------
#  Measurement (called by the operations cycle)
# ---------------------------------------------------------------------
async def measure_goals(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    metrics: dict,
    now: datetime | None = None,
) -> int:
    """Update every active, measurable goal's current_value from a fresh metric
    snapshot; flip to 'achieved' when the target is met. Deterministic. Returns
    the number of goals newly achieved. Does not commit."""
    now = now or datetime.now(UTC)
    goals = await list_goals(session, brand_id=brand_id, only_active=True)
    newly_achieved = 0
    for g in goals:
        key = snapshot_key_for(g.metric)
        if key is None or key not in metrics:
            continue
        try:
            g.current_value = float(metrics[key])
        except (TypeError, ValueError):
            continue
        g.last_measured_at = now
        if is_achieved(g):
            g.status = "achieved"
            g.achieved_at = now
            newly_achieved += 1
    return newly_achieved


# ---------------------------------------------------------------------
#  Feed into the reasoning modules (Strategy / Planner / Decision)
# ---------------------------------------------------------------------
def _goal_line(g: OperationalGoal) -> str:
    if not g.measurable:
        return (
            f"{g.title} ({g.metric}): target {g.target_value:g} — not yet "
            f"measurable from current data; treat as directional."
        )
    frac = progress_fraction(g)
    pct = f"{frac * 100:.0f}%" if frac is not None else "n/a"
    return (
        f"{g.title}: {g.goal_type} {g.metric} to {g.target_value:g} "
        f"(now {g.current_value:g}, {pct} there)."
    )


async def active_goal_summaries(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int = 6
) -> list[str]:
    """Short lines for the brand's active goals + real progress (for structured
    consumers like the Decision Engine). Empty when no goals — never invented."""
    goals = await list_goals(session, brand_id=brand_id, only_active=True)
    return [_goal_line(g) for g in goals[:limit]]


async def active_goals_context(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int = 6
) -> str:
    """A prompt block of the brand's active goals + real progress. Empty-safe:
    states when there are no goals rather than inventing any."""
    lines = await active_goal_summaries(session, brand_id=brand_id, limit=limit)
    if not lines:
        return (
            "BUSINESS GOALS: none set yet — optimise for healthy lead + revenue "
            "growth and suggest the owner set explicit goals."
        )
    return "BUSINESS GOALS (work toward these; ground recommendations in them):\n" + "\n".join(
        f"- {ln}" for ln in lines
    )
