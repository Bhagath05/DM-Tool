"""CRM core service (Phase 6.5) — pipelines, stages, deals, analytics.

Everything brand-scoped (every read/write filters by tenant.brand_id) and
audited via the reused audit service. The stage-move state machine derives a
deal's status/probability from the target stage (is_won/is_lost) and records an
immutable DealStageEvent — the deal's activity timeline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.crm import ai
from aicmo.modules.crm.models import (
    Deal,
    DealStageEvent,
    Pipeline,
    PipelineStage,
)
from aicmo.modules.crm.schemas import (
    DealCreate,
    DealUpdate,
    PipelineAnalytics,
    PipelineCreate,
    StageBreakdown,
    StageInput,
)
from aicmo.tenancy.context import TenantContext

# A sensible default pipeline so a brand's CRM is usable immediately (never
# fabricated data — just an empty, standard sales funnel to drop deals into).
_DEFAULT_STAGES = [
    StageInput(name="New", probability=10),
    StageInput(name="Qualified", probability=30),
    StageInput(name="Proposal", probability=55),
    StageInput(name="Negotiation", probability=75),
    StageInput(name="Won", probability=100, is_won=True),
    StageInput(name="Lost", probability=0, is_lost=True),
]


async def _audit(session, *, tenant, action, target_id, metadata=None):
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action=action, brand_id=tenant.brand_id, target_type="crm", target_id=target_id,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------
#  Pipelines + stages
# ---------------------------------------------------------------------
async def _stages_for(session: AsyncSession, pipeline_id: uuid.UUID) -> list[PipelineStage]:
    rows = await session.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_id == pipeline_id)
        .order_by(PipelineStage.position)
    )
    return list(rows.scalars().all())


def _new_stages(tenant: TenantContext, pipeline_id: uuid.UUID, stages: list[StageInput]) -> list[PipelineStage]:
    return [
        PipelineStage(
            id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
            pipeline_id=pipeline_id, name=s.name, position=i, probability=s.probability,
            is_won=s.is_won, is_lost=s.is_lost,
        )
        for i, s in enumerate(stages)
    ]


async def ensure_default_pipeline(session: AsyncSession, *, tenant: TenantContext) -> Pipeline:
    """Return the brand's default pipeline, creating a standard one on first use."""
    existing = await session.scalar(
        select(Pipeline).where(
            Pipeline.brand_id == tenant.brand_id, Pipeline.is_default.is_(True),
            Pipeline.archived.is_(False),
        )
    )
    if existing is not None:
        return existing
    pipeline = Pipeline(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name="Sales", kind="sales", is_default=True, created_by_user_id=tenant.user_id,
    )
    session.add(pipeline)
    for stage in _new_stages(tenant, pipeline.id, _DEFAULT_STAGES):
        session.add(stage)
    await session.commit()
    await session.refresh(pipeline)
    return pipeline


async def list_pipelines(session: AsyncSession, *, tenant: TenantContext) -> list[tuple[Pipeline, list[PipelineStage]]]:
    await ensure_default_pipeline(session, tenant=tenant)
    rows = await session.execute(
        select(Pipeline)
        .where(Pipeline.brand_id == tenant.brand_id, Pipeline.archived.is_(False))
        .order_by(Pipeline.is_default.desc(), Pipeline.created_at)
    )
    pipelines = list(rows.scalars().all())
    return [(p, await _stages_for(session, p.id)) for p in pipelines]


async def create_pipeline(
    session: AsyncSession, *, tenant: TenantContext, payload: PipelineCreate
) -> tuple[Pipeline, list[PipelineStage]]:
    pipeline = Pipeline(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=payload.name, kind=payload.kind, created_by_user_id=tenant.user_id,
    )
    session.add(pipeline)
    stages = payload.stages or _DEFAULT_STAGES
    for stage in _new_stages(tenant, pipeline.id, stages):
        session.add(stage)
    await _audit(session, tenant=tenant, action="crm.pipeline_created", target_id=pipeline.id,
                 metadata={"name": payload.name, "kind": payload.kind})
    await session.commit()
    await session.refresh(pipeline)
    return pipeline, await _stages_for(session, pipeline.id)


async def _owned_pipeline(session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID) -> Pipeline:
    row = await session.get(Pipeline, pipeline_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found.")
    return row


async def update_pipeline(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID,
    name: str | None, archived: bool | None,
) -> tuple[Pipeline, list[PipelineStage]]:
    p = await _owned_pipeline(session, tenant=tenant, pipeline_id=pipeline_id)
    if name is not None:
        p.name = name
    if archived is not None:
        p.archived = archived
    await session.commit()
    await session.refresh(p)
    return p, await _stages_for(session, p.id)


async def add_stage(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID, stage: StageInput
) -> PipelineStage:
    await _owned_pipeline(session, tenant=tenant, pipeline_id=pipeline_id)
    existing = await _stages_for(session, pipeline_id)
    row = _new_stages(tenant, pipeline_id, [stage])[0]
    row.position = len(existing)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def reorder_stages(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID, stage_ids: list[uuid.UUID]
) -> list[PipelineStage]:
    await _owned_pipeline(session, tenant=tenant, pipeline_id=pipeline_id)
    stages = {s.id: s for s in await _stages_for(session, pipeline_id)}
    for pos, sid in enumerate(stage_ids):
        if sid in stages:
            stages[sid].position = pos
    await session.commit()
    return await _stages_for(session, pipeline_id)


async def delete_stage(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID, stage_id: uuid.UUID
) -> None:
    await _owned_pipeline(session, tenant=tenant, pipeline_id=pipeline_id)
    stage = await session.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != pipeline_id or stage.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found.")
    await session.delete(stage)  # deals.stage_id → SET NULL
    await session.commit()


# ---------------------------------------------------------------------
#  Deals
# ---------------------------------------------------------------------
async def _owned_deal(session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID) -> Deal:
    row = await session.get(Deal, deal_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    return row


async def create_deal(session: AsyncSession, *, tenant: TenantContext, payload: DealCreate) -> Deal:
    await _owned_pipeline(session, tenant=tenant, pipeline_id=payload.pipeline_id)
    stage_id = payload.stage_id
    prob = payload.probability
    if stage_id is not None:
        stage = await session.get(PipelineStage, stage_id)
        if stage is None or stage.pipeline_id != payload.pipeline_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stage does not belong to the pipeline.")
        if prob is None:
            prob = stage.probability
    deal = Deal(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        pipeline_id=payload.pipeline_id, stage_id=stage_id, lead_id=payload.lead_id,
        title=payload.title, company=payload.company, contact_name=payload.contact_name,
        contact_email=payload.contact_email, contact_phone=payload.contact_phone,
        value=payload.value, currency=payload.currency.upper(), probability=prob,
        priority=payload.priority, expected_close_date=payload.expected_close_date,
        owner_user_id=payload.owner_user_id or tenant.user_id, source=payload.source,
        tags=payload.tags, products=[p.model_dump() for p in payload.products],
        competitors=payload.competitors,
    )
    session.add(deal)
    await _audit(session, tenant=tenant, action="crm.deal_created", target_id=deal.id,
                 metadata={"title": payload.title, "value": payload.value})
    await session.commit()
    await session.refresh(deal)
    return deal


async def list_deals(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None, deal_status: str | None = None,
    owner_user_id: str | None = None, q: str | None = None,
    limit: int = 100, offset: int = 0,
) -> tuple[list[Deal], int]:
    conds = [Deal.brand_id == tenant.brand_id]
    if pipeline_id is not None:
        conds.append(Deal.pipeline_id == pipeline_id)
    if stage_id is not None:
        conds.append(Deal.stage_id == stage_id)
    if deal_status is not None:
        conds.append(Deal.status == deal_status)
    if owner_user_id is not None:
        conds.append(Deal.owner_user_id == owner_user_id)
    if q:
        like = f"%{q.strip()}%"
        conds.append(Deal.title.ilike(like) | Deal.company.ilike(like))
    total = (await session.execute(select(func.count()).select_from(Deal).where(*conds))).scalar_one()
    rows = await session.execute(
        select(Deal).where(*conds).order_by(Deal.updated_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def update_deal(
    session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID, payload: DealUpdate
) -> Deal:
    deal = await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    data = payload.model_dump(exclude_unset=True)
    if "products" in data and data["products"] is not None:
        data["products"] = [p if isinstance(p, dict) else p.model_dump() for p in payload.products]
    if data.get("currency"):
        data["currency"] = data["currency"].upper()
    for k, v in data.items():
        setattr(deal, k, v)
    await session.commit()
    await session.refresh(deal)
    return deal


async def move_deal(
    session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID,
    stage_id: uuid.UUID, note: str | None = None,
) -> Deal:
    """Move a deal to a stage (drag-drop). Derives status + probability from the
    stage and records an immutable stage event."""
    deal = await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    stage = await session.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != deal.pipeline_id or stage.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stage does not belong to this deal's pipeline.")

    from_stage, from_status = deal.stage_id, deal.status
    now = datetime.now(UTC)
    deal.stage_id = stage_id
    deal.probability = stage.probability
    if stage.is_won:
        deal.status = "won"
        deal.won_at = now
    elif stage.is_lost:
        deal.status = "lost"
        deal.lost_at = now
    else:
        deal.status = "open"

    session.add(DealStageEvent(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        deal_id=deal.id, from_stage_id=from_stage, to_stage_id=stage_id,
        from_status=from_status, to_status=deal.status, actor_user_id=tenant.user_id, note=note,
    ))
    # Slice 3 automation — auto-draft a grounded follow-up (staged, atomic).
    from aicmo.modules.crm import automation

    if deal.status == "won":
        automation.on_deal_won(session, tenant=tenant, deal=deal)
    elif deal.status == "lost":
        automation.on_deal_lost(session, tenant=tenant, deal=deal)
    else:
        automation.on_deal_moved(session, tenant=tenant, deal=deal, stage_name=stage.name)
    await _audit(session, tenant=tenant, action="crm.deal_moved", target_id=deal.id,
                 metadata={"to_stage": str(stage_id), "status": deal.status})
    await session.commit()
    await session.refresh(deal)
    return deal


async def close_deal(
    session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID,
    close_status: str, lost_reason: str | None,
) -> Deal:
    deal = await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    from_status = deal.status
    now = datetime.now(UTC)
    deal.status = close_status
    if close_status == "won":
        deal.won_at = now
        deal.probability = 100
    else:
        deal.lost_at = now
        deal.lost_reason = lost_reason
        deal.probability = 0
    session.add(DealStageEvent(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        deal_id=deal.id, from_stage_id=deal.stage_id, to_stage_id=deal.stage_id,
        from_status=from_status, to_status=close_status, actor_user_id=tenant.user_id,
        note=lost_reason,
    ))
    from aicmo.modules.crm import automation

    (automation.on_deal_won if close_status == "won" else automation.on_deal_lost)(
        session, tenant=tenant, deal=deal
    )
    await _audit(session, tenant=tenant, action="crm.deal_closed", target_id=deal.id,
                 metadata={"status": close_status})
    await session.commit()
    await session.refresh(deal)
    return deal


async def delete_deal(session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID) -> None:
    deal = await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    await session.delete(deal)
    await session.commit()


async def deal_events(session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID) -> list[DealStageEvent]:
    await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    rows = await session.execute(
        select(DealStageEvent).where(DealStageEvent.deal_id == deal_id).order_by(DealStageEvent.created_at)
    )
    return list(rows.scalars().all())


async def generate_next_action(session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID) -> Deal:
    deal = await _owned_deal(session, tenant=tenant, deal_id=deal_id)
    action = await ai.next_action(session, deal)
    deal.ai_next_action = action.model_dump()
    deal.ai_generated_at = datetime.now(UTC)
    await _audit(session, tenant=tenant, action="crm.deal_next_action", target_id=deal.id,
                 metadata={"confidence": action.confidence})
    await session.commit()
    await session.refresh(deal)
    return deal


# ---------------------------------------------------------------------
#  Analytics (Part 9)
# ---------------------------------------------------------------------
async def analytics(
    session: AsyncSession, *, tenant: TenantContext, pipeline_id: uuid.UUID | None = None
) -> PipelineAnalytics:
    conds = [Deal.brand_id == tenant.brand_id]
    if pipeline_id is not None:
        conds.append(Deal.pipeline_id == pipeline_id)

    async def _count(*extra) -> int:
        return int((await session.execute(
            select(func.count()).select_from(Deal).where(*conds, *extra)
        )).scalar_one())

    async def _sum(col, *extra) -> float:
        return float((await session.execute(
            select(func.coalesce(func.sum(col), 0)).where(*conds, *extra)
        )).scalar_one())

    open_deals = await _count(Deal.status == "open")
    won_deals = await _count(Deal.status == "won")
    lost_deals = await _count(Deal.status == "lost")
    pipeline_value = await _sum(Deal.value, Deal.status == "open")
    won_value = await _sum(Deal.value, Deal.status == "won")

    # Weighted forecast — Σ open value × probability/100 (stage/deal probability).
    forecast_rows = await session.execute(
        select(Deal.value, Deal.probability).where(*conds, Deal.status == "open")
    )
    weighted_forecast = round(
        sum(float(v) * ((p if p is not None else 0) / 100.0) for v, p in forecast_rows.all()), 2
    )

    total_closed = won_deals + lost_deals
    total = open_deals + won_deals + lost_deals
    win_rate = round(won_deals / total_closed, 4) if total_closed else 0.0
    avg_deal_size = round(won_value / won_deals, 2) if won_deals else 0.0
    conversion_rate = round(won_deals / total, 4) if total else 0.0

    # By-stage breakdown (open deals only — the live funnel).
    stage_rows = await session.execute(
        select(
            Deal.stage_id, func.count(), func.coalesce(func.sum(Deal.value), 0)
        ).where(*conds, Deal.status == "open").group_by(Deal.stage_id)
    )
    stage_names: dict[uuid.UUID, str] = {}
    if pipeline_id is not None:
        for st in await _stages_for(session, pipeline_id):
            stage_names[st.id] = st.name
    by_stage = [
        StageBreakdown(
            stage_id=sid, stage_name=stage_names.get(sid, "Unassigned") if sid else "Unassigned",
            count=int(cnt), value=float(val),
        )
        for sid, cnt, val in stage_rows.all()
    ]

    return PipelineAnalytics(
        pipeline_id=pipeline_id, open_deals=open_deals, won_deals=won_deals, lost_deals=lost_deals,
        pipeline_value=round(pipeline_value, 2), weighted_forecast=weighted_forecast,
        won_value=round(won_value, 2), win_rate=win_rate, avg_deal_size=avg_deal_size,
        conversion_rate=conversion_rate, by_stage=by_stage,
    )
