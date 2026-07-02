"""Module 6 — read/mutate the stored LearningInsight rows for the API."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.learning.insights_schemas import LearningInsightResponse
from aicmo.modules.learning.models import LearningInsight


async def list_insights(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    only_active: bool = True,
    category: str | None = None,
    limit: int = 50,
) -> list[LearningInsightResponse]:
    stmt = select(LearningInsight).where(LearningInsight.brand_id == brand_id)
    if only_active:
        stmt = stmt.where(LearningInsight.status == "active")
    if category:
        stmt = stmt.where(LearningInsight.category == category)
    stmt = stmt.order_by(
        desc(LearningInsight.confidence),
        desc(LearningInsight.learned_at),
    ).limit(max(1, min(limit, 200)))
    rows = (await session.execute(stmt)).scalars().all()
    return [LearningInsightResponse.model_validate(r) for r in rows]


async def archive_insight(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    insight_id: uuid.UUID,
) -> LearningInsightResponse | None:
    row = await session.get(LearningInsight, insight_id)
    if row is None or row.brand_id != brand_id:
        return None
    row.status = "archived"
    await session.flush()
    return LearningInsightResponse.model_validate(row)
