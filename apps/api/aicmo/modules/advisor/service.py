"""Advisor service — persist, status updates, history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.dedupe import (
    fingerprint_for_hero,
    fingerprint_for_opportunity,
    impact_label,
    recommendation_id_from_fingerprint,
)
from aicmo.modules.advisor.memory import append_memory_event
from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
from aicmo.modules.advisor.schemas import (
    AdvisorHistoryItem,
    AdvisorRecommendationResponse,
    DataSourceRef,
    IntelligenceRecommendation,
    RecommendationStatus,
)
from aicmo.modules.opportunities.schemas import (
    Opportunity,
    OpportunityCenterReport,
    OpportunityHeroRecommendation,
    derive_opportunity_id,
)
from aicmo.tenancy.context import TenantContext


def _parse_data_used(raw: list | None) -> list[DataSourceRef]:
    out: list[DataSourceRef] = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append(
                DataSourceRef(
                    key=str(item.get("key", "")),
                    label=str(item.get("label", "")),
                    value=str(item.get("value", "")),
                )
            )
    return out


def _to_response(row: AdvisorRecommendation) -> AdvisorRecommendationResponse:
    return AdvisorRecommendationResponse(
        id=row.id,
        record_type=row.record_type,
        title=row.title,
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        impact_score=row.impact_score,
        confidence=row.confidence,
        impact_category=row.impact_category,  # type: ignore[arg-type]
        why=row.why,
        data_used=_parse_data_used(row.data_used),
        expected_result=row.expected_result,
        source_surface=row.source_surface,
        outcome_summary=row.outcome_summary,
        repeat_rationale=row.repeat_rationale,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        skipped_at=row.skipped_at,
    )


async def get_recommendation(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    recommendation_id: uuid.UUID,
) -> AdvisorRecommendation | None:
    stmt = select(AdvisorRecommendation).where(
        AdvisorRecommendation.brand_id == brand_id,
        AdvisorRecommendation.id == recommendation_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
    status: RecommendationStatus,
) -> AdvisorRecommendationResponse:
    row = await get_recommendation(
        session, brand_id=tenant.brand_id, recommendation_id=recommendation_id
    )
    if row is None:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )

    old_status = row.status
    row.status = status
    now = datetime.now(UTC)
    if status == "completed":
        row.completed_at = now
        row.skipped_at = None
        from aicmo.config import get_settings
        from aicmo.modules.advisor.outcomes import schedule_outcome_evaluation

        if get_settings().advisor_outcome_learning_enabled:
            await schedule_outcome_evaluation(
                session, brand_id=tenant.brand_id, recommendation=row
            )
    elif status == "skipped":
        row.skipped_at = now
        row.completed_at = None
        row.outcome_summary = "Skipped — marked as not relevant for this business."
        from aicmo.config import get_settings
        from aicmo.modules.advisor.outcomes import record_skipped_outcome

        if get_settings().advisor_outcome_learning_enabled:
            await record_skipped_outcome(
                session, brand_id=tenant.brand_id, recommendation=row
            )
    elif status == "not_started":
        row.completed_at = None
        row.skipped_at = None

    await append_memory_event(
        session,
        recommendation_id=row.id,
        event_type="status_changed",
        payload={"from": old_status, "to": status},
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


async def list_history(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 50,
) -> list[AdvisorHistoryItem]:
    stmt = (
        select(AdvisorRecommendation, AdvisorOutcome)
        .outerjoin(
            AdvisorOutcome,
            AdvisorOutcome.recommendation_id == AdvisorRecommendation.id,
        )
        .where(
            AdvisorRecommendation.brand_id == brand_id,
            AdvisorRecommendation.record_type == "recommendation_created",
        )
        .order_by(desc(AdvisorRecommendation.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items: list[AdvisorHistoryItem] = []
    for row, outcome in rows:
        learning = _learning_summary(row, outcome)
        items.append(
            AdvisorHistoryItem(
                id=row.id,
                date=row.created_at.strftime("%B %d, %Y"),
                title=row.title,
                description=row.description,
                status=row.status,  # type: ignore[arg-type]
                observation=row.observation or row.title,
                root_cause=row.root_cause or row.why,
                recommended_action=row.description,
                expected_impact=row.expected_result,
                result_summary=row.outcome_summary,
                outcome_status=outcome.evaluation_status if outcome else None,
                effectiveness_score=outcome.effectiveness_score if outcome else None,
                learning=learning,
                impact_score=row.impact_score,
                impact_label=impact_label(row.impact_score),  # type: ignore[arg-type]
                confidence=row.confidence,
                why=row.why,
                data_used=_parse_data_used(row.data_used),
                expected_result=row.expected_result,
            )
        )
    return items


def _learning_summary(
    row: AdvisorRecommendation, outcome: AdvisorOutcome | None
) -> str | None:
    if row.repeat_rationale:
        return row.repeat_rationale
    if outcome and outcome.delta_summary:
        if outcome.effectiveness_score is not None and outcome.effectiveness_score >= 55:
            return f"Worked: {outcome.delta_summary}"
        if outcome.effectiveness_score is not None and outcome.effectiveness_score < 45:
            return f"Underperformed: {outcome.delta_summary}"
        return outcome.delta_summary
    if row.status == "skipped":
        return "Skipped — similar actions deprioritized in future recommendations."
    return None


async def upsert_intelligence_rec(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    rec_id: uuid.UUID,
    fingerprint: str,
    rec: IntelligenceRecommendation,
    source_surface: str,
    title: str,
) -> AdvisorRecommendation:
    data_used = [d.model_dump(mode="json") for d in rec.data_sources_used]
    return await _upsert_recommendation(
        session,
        tenant=tenant,
        rec_id=rec_id,
        fingerprint=fingerprint,
        title=title,
        description=rec.recommended_action,
        source_surface=source_surface,
        confidence=rec.confidence,
        impact_category=rec.impact_category,
        why=rec.root_cause,
        expected_result=rec.expected_impact,
        data_used=data_used,
        generator_hint=rec.generator_hint,
        impact_score=rec.confidence,
        observation=rec.observation,
        root_cause=rec.root_cause,
    )


async def _upsert_recommendation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    rec_id: uuid.UUID,
    fingerprint: str,
    title: str,
    description: str,
    source_surface: str,
    confidence: int,
    impact_category: str | None,
    why: str | None,
    expected_result: str | None,
    data_used: list[dict[str, str]],
    generator_hint: dict[str, Any] | None,
    impact_score: int | None = None,
    observation: str | None = None,
    root_cause: str | None = None,
) -> AdvisorRecommendation:
    existing = (
        await session.execute(
            select(AdvisorRecommendation).where(
                AdvisorRecommendation.brand_id == tenant.brand_id,
                AdvisorRecommendation.id == rec_id,
            )
        )
    ).scalar_one_or_none()

    score = impact_score if impact_score is not None else min(100, confidence)

    if existing:
        existing.title = title
        existing.description = description
        existing.confidence = confidence
        existing.impact_score = score
        existing.impact_category = impact_category
        existing.why = why
        existing.expected_result = expected_result
        existing.data_used = data_used
        existing.generator_hint = generator_hint
        existing.source_fingerprint = fingerprint
        if observation is not None:
            existing.observation = observation
        if root_cause is not None:
            existing.root_cause = root_cause
        return existing

    row = AdvisorRecommendation(
        id=rec_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        record_type="recommendation_created",
        title=title,
        description=description,
        status="not_started",
        impact_score=score,
        confidence=confidence,
        impact_category=impact_category,
        why=why,
        observation=observation,
        root_cause=root_cause,
        data_used=data_used,
        expected_result=expected_result,
        source_surface=source_surface,
        source_fingerprint=fingerprint,
        generator_hint=generator_hint,
    )
    session.add(row)
    await session.flush()
    await append_memory_event(
        session,
        recommendation_id=rec_id,
        event_type="created",
        payload={"source_surface": source_surface},
    )
    return row


def _data_used_from_signals(signals: list[str]) -> list[dict[str, str]]:
    return [
        {"key": f"signal_{i}", "label": "Signal", "value": s[:200]}
        for i, s in enumerate(signals[:6])
    ]


async def persist_opportunity_report(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    report: OpportunityCenterReport,
    signals: list[str],
) -> OpportunityCenterReport:
    """Upsert advisor rows and attach task_status to each opportunity."""

    async def persist_opp(opp: Opportunity, surface: str) -> Opportunity:
        fp = fingerprint_for_opportunity(
            kind=opp.kind,
            generator=opp.generator,
            recommended_action=opp.recommended_action,
        )
        rec_id = derive_opportunity_id(
            kind=opp.kind,
            generator=opp.generator,
            recommended_action=opp.recommended_action,
        )
        row = await _upsert_recommendation(
            session,
            tenant=tenant,
            rec_id=rec_id,
            fingerprint=fp,
            title=opp.headline,
            description=opp.recommended_action,
            source_surface=surface,
            confidence=opp.confidence,
            impact_category=opp.impact_category,
            why=opp.why_it_matters,
            expected_result=opp.expected_result,
            data_used=_data_used_from_signals(opp.evidence or signals),
            generator_hint=opp.generator.model_dump(mode="json"),
        )
        return opp.model_copy(update={"task_status": row.status})

    hero = report.hero_recommendation
    hero_fp = fingerprint_for_hero(hero.recommendation)
    hero_id = recommendation_id_from_fingerprint(hero_fp)
    hero_row = await _upsert_recommendation(
        session,
        tenant=tenant,
        rec_id=hero_id,
        fingerprint=hero_fp,
        title="Today's top action",
        description=hero.recommendation,
        source_surface="opportunity_hero",
        confidence=hero.confidence,
        impact_category=hero.impact_category,
        why=hero.reason,
        expected_result=hero.expected_result,
        data_used=_data_used_from_signals(signals),
        generator_hint=None,
        impact_score=hero.confidence,
    )
    hero_with_status = hero.model_copy(update={"task_status": hero_row.status})

    content = []
    for opp in report.content_opportunities:
        content.append(await persist_opp(opp, "opportunity_content"))
    ads = []
    for opp in report.ad_opportunities:
        ads.append(await persist_opp(opp, "opportunity_ad"))

    await session.commit()
    return report.model_copy(
        update={
            "hero_recommendation": hero_with_status,
            "content_opportunities": content,
            "ad_opportunities": ads,
        }
    )


async def record_activity(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    record_type: str,
    title: str,
    description: str = "",
    linked_asset_type: str | None = None,
    linked_asset_id: uuid.UUID | None = None,
) -> None:
    """Auto-ingest generation / lead events into memory."""
    fp = f"{record_type}|{title}|{linked_asset_id or ''}"
    rec_id = recommendation_id_from_fingerprint(fp)
    existing = await get_recommendation(
        session, brand_id=tenant.brand_id, recommendation_id=rec_id
    )
    if existing:
        return
    row = AdvisorRecommendation(
        id=rec_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        record_type=record_type,
        title=title,
        description=description,
        status="completed",
        impact_score=0,
        confidence=100,
        source_surface="system",
        source_fingerprint=fp,
        linked_asset_type=linked_asset_type,
        linked_asset_id=linked_asset_id,
        completed_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
