"""Module 6 — the Learning Engine's feedback into the reasoning modules.

Deliberately dependency-light: imports ONLY the LearningInsight model so the
four reasoning modules (business_understanding, strategy, planner, decision)
can inherit learned lessons without any import cycle back through the heavy
synthesis engine.

`learning_context_block(...)` returns a short prompt block; the reasoning
prompts paste it in so decisions/strategy/plans are grounded in what has
actually worked for THIS brand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.learning.models import LearningInsight

# Only lessons at/above this confidence feed the reasoning modules — same floor
# the synthesis engine persists at.
_MIN_CONFIDENCE = 40


async def active_insights_for_module(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    module: str,
    limit: int = 6,
) -> list[LearningInsight]:
    """Active, unexpired lessons that should influence `module`, strongest
    first. Filtered in Python on the (small) active set so we don't depend on
    a JSONB containment operator."""
    now = datetime.now(UTC)
    stmt = (
        select(LearningInsight)
        .where(
            LearningInsight.brand_id == brand_id,
            LearningInsight.status == "active",
            LearningInsight.confidence >= _MIN_CONFIDENCE,
        )
        .order_by(
            desc(LearningInsight.confidence),
            desc(LearningInsight.learned_at),
        )
        .limit(50)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    out: list[LearningInsight] = []
    for row in rows:
        if row.expires_at is not None and row.expires_at < now:
            continue
        if module in (row.affected_modules or []):
            out.append(row)
        if len(out) >= limit:
            break
    return out


def render_insights_block(rows: list[LearningInsight]) -> str:
    """Format lessons for prompt injection. Never fabricates — an empty set
    yields an explicit 'nothing learned yet' line."""
    if not rows:
        return (
            "LEARNED LESSONS: none yet — not enough history has been analysed "
            "for this brand. Do not assume any past result."
        )
    lines = [
        "LEARNED LESSONS (what has actually worked/failed for this brand — "
        "prefer these over guesses; a negative lesson means do NOT repeat it):"
    ]
    for r in rows:
        arrow = {"positive": "✓", "negative": "✗"}.get(r.direction, "•")
        lines.append(
            f"- {arrow} [{r.category}] {r.observation} "
            f"(confidence {r.confidence}%) → {r.recommendation}"
        )
    return "\n".join(lines)


async def learning_context_block(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    module: str,
    limit: int = 6,
) -> str:
    """Convenience: fetch + render in one call for a reasoning prompt."""
    rows = await active_insights_for_module(
        session, brand_id=brand_id, module=module, limit=limit
    )
    return render_insights_block(rows)
