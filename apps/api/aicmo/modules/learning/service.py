"""Learning Lab service — CRUD + the public API generators call.

Two distinct surfaces:

1. **Public service helpers** for generators:
   - `record_experiment(...)` — write a CampaignExperiment row.
   - `record_result(...)` — snapshot a perf row for an existing experiment.
   - `top_learning_events_for_context(...)` — feeds GenerationContext.
   - `provenance_for_asset(...)` — feeds the WhyGeneratedCard.

2. **Read APIs** for the Lab UI:
   - `list_experiments`, `list_results`, `list_learning_events`.

All async + DB-bound. The router stays thin and just calls these.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.learning.models import (
    CampaignExperiment,
    ExperimentResult,
    LearningEvent,
)
from aicmo.tenancy.context import TenantContext  # noqa: F401  (used by string-annotation in record_experiment)
from aicmo.modules.learning.schemas import (
    CampaignExperimentResponse,
    ExperimentProvenance,
    ExperimentResultResponse,
    LearningEventResponse,
    RecordExperimentInput,
    RecordResultInput,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Write paths — called by generators / result-attribution
# ---------------------------------------------------------------------


async def record_experiment(
    session: AsyncSession,
    *,
    tenant: "TenantContext",
    payload: RecordExperimentInput,
) -> CampaignExperimentResponse:
    """Persist a provenance row. Idempotent on (brand, source_asset_id)."""
    existing = await session.execute(
        select(CampaignExperiment).where(
            CampaignExperiment.brand_id == tenant.brand_id,
            CampaignExperiment.source_asset_id == payload.source_asset_id,
        )
    )
    row = existing.scalar_one_or_none()

    if row is None:
        row = CampaignExperiment(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            source_asset_type=payload.source_asset_type,
            source_asset_id=payload.source_asset_id,
            platform=payload.platform,
            goal=payload.goal,
            hypothesis=payload.hypothesis,
            inherited_patterns=list(payload.inherited_patterns or []),
            variable_choices=dict(payload.variable_choices or {}),
            context_snapshot=dict(payload.context_snapshot or {}),
            status="pending",
        )
        session.add(row)
    else:
        row.source_asset_type = payload.source_asset_type
        row.platform = payload.platform
        row.goal = payload.goal
        row.hypothesis = payload.hypothesis
        row.inherited_patterns = list(payload.inherited_patterns or [])
        row.variable_choices = dict(payload.variable_choices or {})
        row.context_snapshot = dict(payload.context_snapshot or {})

    await session.flush()
    return CampaignExperimentResponse.model_validate(row)


async def record_result(
    session: AsyncSession,
    *,
    payload: RecordResultInput,
) -> ExperimentResultResponse:
    """Snapshot a result row + flip the parent experiment's status.

    `engagement_rate` is computed here so the call site doesn't have to
    keep the formula in two places. `sample_size` on the result row =
    impressions at snapshot time (small impression counts shouldn't
    drive confident conclusions).
    """
    parent = await session.get(CampaignExperiment, payload.experiment_id)
    if parent is None:
        raise ValueError(
            f"experiment {payload.experiment_id} not found"
        )

    denom = max(payload.impressions or payload.reach or payload.views or 1, 1)
    engagement = (
        payload.likes
        + payload.comments_count
        + payload.saves
        + payload.shares
    )
    engagement_rate = round(engagement / denom, 4)

    row = ExperimentResult(
        id=uuid.uuid4(),
        experiment_id=payload.experiment_id,
        impressions=payload.impressions,
        reach=payload.reach,
        likes=payload.likes,
        comments_count=payload.comments_count,
        saves=payload.saves,
        shares=payload.shares,
        engagement_rate=engagement_rate,
        leads=payload.leads,
        ctr=payload.ctr,
        views=payload.views,
        watch_time_seconds=payload.watch_time_seconds,
        raw_json=dict(payload.raw_json or {}),
        captured_at=datetime.now(UTC),
        sample_size=payload.impressions,
        # Naive but useful default: more impressions → more confident.
        # The engine later overwrites with its own scoring per finding.
        confidence_score=_impression_confidence(payload.impressions),
        evidence=[],
    )
    session.add(row)

    # Promote parent status — once we have any result it counts as "live".
    if parent.status == "pending":
        parent.status = "live"
    # Mark "completed" only when we have a meaningful signal (≥100
    # impressions) — earlier we'd just be looking at noise.
    if payload.impressions >= 100 and parent.status in ("pending", "live"):
        parent.status = "completed"

    await session.flush()
    return ExperimentResultResponse.model_validate(row)


def _impression_confidence(impressions: int) -> float:
    """Naive monotone mapping from impressions → 0.0-1.0. Keeps the UI
    honest before the LLM engine writes its own per-finding score."""
    if impressions <= 0:
        return 0.1
    if impressions < 50:
        return 0.3
    if impressions < 250:
        return 0.5
    if impressions < 1000:
        return 0.7
    return 0.85


# ---------------------------------------------------------------------
#  Reads — for the Lab UI
# ---------------------------------------------------------------------


async def list_experiments(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
) -> list[CampaignExperimentResponse]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(CampaignExperiment)
        .where(CampaignExperiment.brand_id == brand_id)
        .order_by(desc(CampaignExperiment.created_at))
        .limit(limit)
    )
    if status:
        stmt = stmt.where(CampaignExperiment.status == status)
    if platform:
        stmt = stmt.where(CampaignExperiment.platform == platform)
    rows = (await session.execute(stmt)).scalars().all()
    return [CampaignExperimentResponse.model_validate(r) for r in rows]


async def list_results_for_experiment(
    session: AsyncSession,
    *,
    experiment_id: uuid.UUID,
) -> list[ExperimentResultResponse]:
    stmt = (
        select(ExperimentResult)
        .where(ExperimentResult.experiment_id == experiment_id)
        .order_by(desc(ExperimentResult.captured_at))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [ExperimentResultResponse.model_validate(r) for r in rows]


async def list_learning_events(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    variable: str | None = None,
    only_active: bool = True,
    limit: int = 50,
) -> list[LearningEventResponse]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(LearningEvent)
        .where(LearningEvent.brand_id == brand_id)
        .order_by(
            desc(LearningEvent.confidence_score),
            desc(LearningEvent.created_at),
        )
        .limit(limit)
    )
    if variable:
        stmt = stmt.where(LearningEvent.variable == variable)
    if only_active:
        stmt = stmt.where(LearningEvent.status == "active")
    rows = (await session.execute(stmt)).scalars().all()
    return [LearningEventResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------
#  Provenance — feeds the WhyGeneratedCard
# ---------------------------------------------------------------------


async def provenance_for_asset(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    source_asset_id: uuid.UUID,
) -> ExperimentProvenance | None:
    """One-shot fetch: experiment row + latest result + any LearningEvents
    whose `variable` matches a key in the experiment's variable_choices.

    Returns None when the asset was never recorded (legacy generations
    pre-Phase-1B). Callers should fall back to "no provenance" gracefully.
    """
    exp_stmt = select(CampaignExperiment).where(
        CampaignExperiment.brand_id == brand_id,
        CampaignExperiment.source_asset_id == source_asset_id,
    )
    exp = (await session.execute(exp_stmt)).scalar_one_or_none()
    if exp is None:
        return None

    # Latest result snapshot.
    res_stmt = (
        select(ExperimentResult)
        .where(ExperimentResult.experiment_id == exp.id)
        .order_by(desc(ExperimentResult.captured_at))
        .limit(1)
    )
    latest = (await session.execute(res_stmt)).scalar_one_or_none()

    # Match learning events on the variables this experiment touched.
    variables_touched = list((exp.variable_choices or {}).keys())
    matched: list[LearningEvent] = []
    if variables_touched:
        ev_stmt = (
            select(LearningEvent)
            .where(
                LearningEvent.brand_id == brand_id,
                LearningEvent.status == "active",
                LearningEvent.variable.in_(variables_touched),
            )
            .order_by(desc(LearningEvent.confidence_score))
            .limit(6)
        )
        matched = list((await session.execute(ev_stmt)).scalars().all())

    return ExperimentProvenance(
        experiment=CampaignExperimentResponse.model_validate(exp),
        matched_events=[
            LearningEventResponse.model_validate(e) for e in matched
        ],
        latest_result=ExperimentResultResponse.model_validate(latest)
        if latest
        else None,
    )


# ---------------------------------------------------------------------
#  GenerationContext bridge
# ---------------------------------------------------------------------


async def top_learning_events_for_context(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 5,
    min_confidence: float = 0.55,
    min_sample_size: int = 3,
) -> list[LearningEvent]:
    """What `modules/context/builder.py` calls.

    Returns ORM rows (no Pydantic round-trip) so the builder can cherry-
    pick `.finding`, `.confidence_score`, `.direction` without paying
    for full validation. The thresholds here are the platform-wide rule
    for "we trust this enough to feed it back into generation".
    """
    stmt = (
        select(LearningEvent)
        .where(
            LearningEvent.brand_id == brand_id,
            LearningEvent.status == "active",
            LearningEvent.confidence_score >= min_confidence,
            LearningEvent.sample_size >= min_sample_size,
        )
        .order_by(
            desc(LearningEvent.confidence_score),
            desc(LearningEvent.created_at),
        )
        .limit(max(1, min(limit, 20)))
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------
#  Status mutations from the UI
# ---------------------------------------------------------------------


async def archive_learning_event(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    event_id: uuid.UUID,
) -> LearningEventResponse | None:
    row = await session.get(LearningEvent, event_id)
    if row is None or row.brand_id != brand_id:
        return None
    row.status = "archived"
    await session.flush()
    return LearningEventResponse.model_validate(row)


async def archive_experiment(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    experiment_id: uuid.UUID,
) -> CampaignExperimentResponse | None:
    row = await session.get(CampaignExperiment, experiment_id)
    if row is None or row.brand_id != brand_id:
        return None
    row.status = "archived"
    await session.flush()
    return CampaignExperimentResponse.model_validate(row)
