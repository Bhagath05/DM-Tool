"""Channel/action effectiveness aggregates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorEffectivenessScore, AdvisorOutcome
from aicmo.modules.advisor.models import AdvisorRecommendation


async def recompute_effectiveness(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> None:
    """Recompute effectiveness scores from evaluated outcomes."""
    stmt = (
        select(AdvisorOutcome, AdvisorRecommendation)
        .join(
            AdvisorRecommendation,
            AdvisorRecommendation.id == AdvisorOutcome.recommendation_id,
        )
        .where(
            AdvisorOutcome.brand_id == brand_id,
            AdvisorOutcome.evaluation_status == "evaluated",
            AdvisorOutcome.effectiveness_score.isnot(None),
        )
    )
    rows = (await session.execute(stmt)).all()

    by_surface: dict[str, list[int]] = {}
    for outcome, rec in rows:
        key = rec.source_surface or "unknown"
        by_surface.setdefault(key, []).append(int(outcome.effectiveness_score or 0))

    now = datetime.now(UTC)
    for dimension_key, scores in by_surface.items():
        if not scores:
            continue
        sample_size = len(scores)
        positive = sum(1 for s in scores if s >= 55)
        success_rate = round(100.0 * positive / sample_size, 2)
        avg_eff = round(sum(scores) / sample_size)

        existing = (
            await session.execute(
                select(AdvisorEffectivenessScore).where(
                    AdvisorEffectivenessScore.brand_id == brand_id,
                    AdvisorEffectivenessScore.dimension == "surface",
                    AdvisorEffectivenessScore.dimension_key == dimension_key,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.sample_size = sample_size
            existing.success_rate = success_rate
            existing.avg_effectiveness = avg_eff
            existing.last_computed_at = now
        else:
            session.add(
                AdvisorEffectivenessScore(
                    id=uuid.uuid4(),
                    brand_id=brand_id,
                    dimension="surface",
                    dimension_key=dimension_key,
                    sample_size=sample_size,
                    success_rate=success_rate,
                    avg_effectiveness=avg_eff,
                    last_computed_at=now,
                )
            )


async def list_effectiveness(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> list[dict]:
    stmt = (
        select(AdvisorEffectivenessScore)
        .where(
            AdvisorEffectivenessScore.brand_id == brand_id,
            AdvisorEffectivenessScore.sample_size >= 1,
        )
        .order_by(desc(AdvisorEffectivenessScore.avg_effectiveness))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "dimension": r.dimension,
            "key": r.dimension_key,
            "label": r.dimension_key.replace("_", " ").title(),
            "success_rate": float(r.success_rate) if r.success_rate is not None else None,
            "avg_effectiveness": r.avg_effectiveness,
            "sample_size": r.sample_size,
        }
        for r in rows
    ]
