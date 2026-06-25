"""Read/write advisor memory for prompt injection and dedupe."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorMemoryEvent, AdvisorRecommendation


async def load_brand_memory(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    days: int = 90,
) -> list[AdvisorRecommendation]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(AdvisorRecommendation)
        .where(
            AdvisorRecommendation.brand_id == brand_id,
            AdvisorRecommendation.created_at >= cutoff,
        )
        .order_by(desc(AdvisorRecommendation.updated_at))
        .limit(200)
    )
    return list((await session.execute(stmt)).scalars().all())


def build_memory_context_block(rows: list[AdvisorRecommendation]) -> str:
    if not rows:
        return "ADVISOR MEMORY: No prior recommendations recorded for this brand."

    lines = ["ADVISOR MEMORY — do NOT repeat completed/skipped actions without new data:"]
    for row in rows[:40]:
        status = row.status
        title = row.title[:120]
        when = row.completed_at or row.skipped_at or row.created_at
        when_str = when.strftime("%Y-%m-%d") if when else "unknown"
        outcome = f" → {row.outcome_summary}" if row.outcome_summary else ""
        lines.append(f"- [{status}] {title} ({when_str}){outcome}")
    lines.append(
        "If you must repeat a similar action, include repeat_rationale citing "
        "a metric change since the last time."
    )
    return "\n".join(lines)


async def append_memory_event(
    session: AsyncSession,
    *,
    recommendation_id: uuid.UUID,
    event_type: str,
    payload: dict | None = None,
) -> None:
    session.add(
        AdvisorMemoryEvent(
            recommendation_id=recommendation_id,
            event_type=event_type,
            payload=payload or {},
        )
    )
