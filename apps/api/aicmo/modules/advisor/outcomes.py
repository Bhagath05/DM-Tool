"""Outcome learning — evaluate completed recommendations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.leads.models import Lead


OUTCOME_EVALUATION_DAYS = 14


async def schedule_outcome_evaluation(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    recommendation: AdvisorRecommendation,
) -> AdvisorOutcome:
    """Create pending outcome row when a recommendation is marked completed."""
    existing = (
        await session.execute(
            select(AdvisorOutcome).where(
                AdvisorOutcome.recommendation_id == recommendation.id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    now = datetime.now(UTC)
    baseline = await _snapshot_metrics(
        session,
        brand_id=brand_id,
        as_of=now,
        recommendation_id=recommendation.id,
    )
    row = AdvisorOutcome(
        id=uuid.uuid4(),
        brand_id=brand_id,
        recommendation_id=recommendation.id,
        evaluation_status="pending",
        baseline_snapshot=baseline,
        outcome_snapshot={},
        evaluate_after=now + timedelta(days=OUTCOME_EVALUATION_DAYS),
    )
    session.add(row)
    return row


async def _snapshot_metrics(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    as_of: datetime,
    window_days: int = 14,
    recommendation_id: uuid.UUID | None = None,
) -> dict:
    """Real metrics only — leads, analytics, and published post performance."""
    cutoff = as_of - timedelta(days=window_days)
    lead_count = (
        await session.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.brand_id == brand_id, Lead.created_at >= cutoff)
        )
    ).scalar_one()
    overview = await analytics_service.overview(session, brand_id=brand_id)
    snapshot = {
        "leads_in_window": int(lead_count),
        "total_leads": overview.total_leads,
        "leads_7d": overview.leads_7d,
        "leads_30d": overview.leads_30d,
        "hot_leads": overview.hot_leads,
        "conversion_rate": overview.conversion_rate,
        "snapshot_at": as_of.isoformat(),
        "window_days": window_days,
    }
    if recommendation_id:
        from aicmo.modules.publishing.performance import (
            snapshot_recommendation_performance,
        )

        publish_metrics = await snapshot_recommendation_performance(
            session, brand_id=brand_id, recommendation_id=recommendation_id
        )
        if publish_metrics:
            snapshot["publish"] = publish_metrics
    return snapshot


async def evaluate_due_outcomes(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID | None = None,
    limit: int = 50,
) -> int:
    """Evaluate pending outcomes whose evaluate_after has passed. Returns count."""
    now = datetime.now(UTC)
    stmt = (
        select(AdvisorOutcome)
        .where(
            AdvisorOutcome.evaluation_status == "pending",
            AdvisorOutcome.evaluate_after <= now,
        )
        .order_by(AdvisorOutcome.evaluate_after)
        .limit(limit)
    )
    if brand_id is not None:
        stmt = stmt.where(AdvisorOutcome.brand_id == brand_id)

    rows = (await session.execute(stmt)).scalars().all()
    evaluated = 0
    for row in rows:
        await _evaluate_one(session, row)
        evaluated += 1
    if evaluated:
        await session.commit()
        from aicmo.modules.advisor.effectiveness import recompute_effectiveness

        if brand_id is not None:
            await recompute_effectiveness(session, brand_id=brand_id)
        else:
            brand_ids = {r.brand_id for r in rows}
            for bid in brand_ids:
                await recompute_effectiveness(session, brand_id=bid)
        await session.commit()
    return evaluated


async def _evaluate_one(session: AsyncSession, outcome: AdvisorOutcome) -> None:
    now = datetime.now(UTC)
    outcome_snapshot = await _snapshot_metrics(
        session,
        brand_id=outcome.brand_id,
        as_of=now,
        recommendation_id=outcome.recommendation_id,
    )
    outcome.outcome_snapshot = outcome_snapshot
    outcome.evaluated_at = now

    baseline = outcome.baseline_snapshot or {}
    baseline_leads = int(baseline.get("leads_in_window", 0))
    outcome_leads = int(outcome_snapshot.get("leads_in_window", 0))
    publish = outcome_snapshot.get("publish") or {}
    publish_reach = int(publish.get("reach", 0) or 0)
    publish_engagement = int(publish.get("engagement", 0) or 0)

    if baseline_leads == 0 and outcome_leads == 0 and publish_reach == 0:
        outcome.evaluation_status = "insufficient_data"
        outcome.delta_summary = "Not enough lead activity to measure impact."
        outcome.effectiveness_score = None
        rec = await session.get(AdvisorRecommendation, outcome.recommendation_id)
        if rec:
            rec.outcome_summary = outcome.delta_summary
        return

    delta = outcome_leads - baseline_leads
    perf_bits: list[str] = []
    if publish_reach > 0:
        perf_bits.append(f"reach {publish_reach:,}")
    if publish_engagement > 0:
        perf_bits.append(f"engagement {publish_engagement:,}")
    perf_suffix = f" Published performance: {', '.join(perf_bits)}." if perf_bits else ""

    if delta > 0:
        outcome.effectiveness_score = min(100, 50 + delta * 10)
        outcome.delta_summary = (
            f"Leads in the 14-day window: {outcome_leads} vs {baseline_leads} "
            f"at completion (+{delta}).{perf_suffix}"
        )
        outcome.evaluation_status = "evaluated"
    elif delta < 0:
        outcome.effectiveness_score = max(0, 40 + delta * 5)
        outcome.delta_summary = (
            f"Leads in the 14-day window: {outcome_leads} vs {baseline_leads} "
            f"at completion ({delta}).{perf_suffix}"
        )
        outcome.evaluation_status = "evaluated"
    else:
        outcome.effectiveness_score = 50
        if perf_bits:
            outcome.effectiveness_score = min(85, 55 + min(publish_engagement // 50, 30))
            outcome.delta_summary = (
                f"Lead volume unchanged ({outcome_leads} leads).{perf_suffix}"
            )
        else:
            outcome.delta_summary = (
                f"Lead volume unchanged in the 14-day window ({outcome_leads} leads)."
            )
        outcome.evaluation_status = "evaluated"

    rec = await session.get(AdvisorRecommendation, outcome.recommendation_id)
    if rec:
        rec.outcome_summary = outcome.delta_summary


async def load_outcome_context(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 10,
) -> dict:
    """Historical outcomes for intelligence prompts — successes and failures."""
    stmt = (
        select(AdvisorOutcome, AdvisorRecommendation)
        .join(
            AdvisorRecommendation,
            AdvisorRecommendation.id == AdvisorOutcome.recommendation_id,
        )
        .where(
            AdvisorOutcome.brand_id == brand_id,
            AdvisorOutcome.evaluation_status == "evaluated",
        )
        .order_by(desc(AdvisorOutcome.evaluated_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    outcomes = []
    for outcome, rec in rows:
        outcomes.append(
            {
                "title": rec.title,
                "delta_summary": outcome.delta_summary,
                "effectiveness_score": outcome.effectiveness_score,
                "source_surface": rec.source_surface,
            }
        )

    failed_stmt = (
        select(AdvisorRecommendation)
        .where(
            AdvisorRecommendation.brand_id == brand_id,
            AdvisorRecommendation.status.in_(["skipped", "completed"]),
            AdvisorRecommendation.record_type == "recommendation_created",
        )
        .order_by(desc(AdvisorRecommendation.updated_at))
        .limit(10)
    )
    failed_rows = (await session.execute(failed_stmt)).scalars().all()
    failed_outcomes = []
    for rec in failed_rows:
        if rec.status == "skipped":
            failed_outcomes.append(
                {
                    "title": rec.title,
                    "reason": "Skipped by user — avoid repeating this action",
                    "delta_summary": rec.outcome_summary,
                }
            )
        elif rec.outcome_summary and "unchanged" in (rec.outcome_summary or "").lower():
            failed_outcomes.append(
                {
                    "title": rec.title,
                    "delta_summary": rec.outcome_summary,
                    "reason": "Completed but no measurable improvement",
                }
            )

    from aicmo.modules.advisor.effectiveness import list_effectiveness

    scores = await list_effectiveness(session, brand_id=brand_id)
    return {
        "recent_outcomes": outcomes,
        "failed_outcomes": failed_outcomes[:5],
        "effectiveness_scores": scores,
    }


async def record_skipped_outcome(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    recommendation: AdvisorRecommendation,
) -> None:
    """Record skipped recommendations so future prompts avoid repeating them."""
    existing = (
        await session.execute(
            select(AdvisorOutcome).where(
                AdvisorOutcome.recommendation_id == recommendation.id
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.evaluation_status = "evaluated"
        existing.delta_summary = "Skipped — do not recommend similar actions."
        existing.effectiveness_score = 0
        existing.evaluated_at = datetime.now(UTC)
        return

    now = datetime.now(UTC)
    session.add(
        AdvisorOutcome(
            id=uuid.uuid4(),
            brand_id=brand_id,
            recommendation_id=recommendation.id,
            evaluation_status="evaluated",
            baseline_snapshot={},
            outcome_snapshot={"skipped": True},
            delta_summary="Skipped — do not recommend similar actions.",
            effectiveness_score=0,
            evaluate_after=now,
            evaluated_at=now,
        )
    )
