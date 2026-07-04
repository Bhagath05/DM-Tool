"""CRM HTTP API (Phase 6.5). Tenant-scoped + RBAC (crm.view / crm.manage) +
audited. Literal paths (/crm/pipelines, /crm/analytics, /crm/deals) register
before the param routes so nothing is captured as an id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.crm import service
from aicmo.modules.crm.models import Pipeline, PipelineStage
from aicmo.modules.crm.schemas import (
    DealCloseRequest,
    DealCreate,
    DealEventList,
    DealEventResponse,
    DealList,
    DealMoveRequest,
    DealResponse,
    DealUpdate,
    PipelineAnalytics,
    PipelineCreate,
    PipelineList,
    PipelineResponse,
    PipelineUpdate,
    ReorderStagesRequest,
    StageInput,
    StageResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm", tags=["crm"])

_VIEW = require_permission("crm.view")
_MANAGE = require_permission("crm.manage")


def _pipeline_response(pipeline: Pipeline, stages: list[PipelineStage]) -> PipelineResponse:
    resp = PipelineResponse.model_validate(pipeline)
    resp.stages = [StageResponse.model_validate(s) for s in stages]
    return resp


# ---- pipelines ----
@router.get("/pipelines", response_model=PipelineList)
async def list_pipelines(
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> PipelineList:
    rows = await service.list_pipelines(session, tenant=tenant)
    return PipelineList(items=[_pipeline_response(p, s) for p, s in rows])


@router.post("/pipelines", response_model=PipelineResponse, status_code=201)
async def create_pipeline(
    payload: PipelineCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> PipelineResponse:
    p, stages = await service.create_pipeline(session, tenant=tenant, payload=payload)
    return _pipeline_response(p, stages)


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: uuid.UUID, payload: PipelineUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> PipelineResponse:
    p, stages = await service.update_pipeline(
        session, tenant=tenant, pipeline_id=pipeline_id, name=payload.name, archived=payload.archived
    )
    return _pipeline_response(p, stages)


@router.post("/pipelines/{pipeline_id}/stages", response_model=StageResponse, status_code=201)
async def add_stage(
    pipeline_id: uuid.UUID, payload: StageInput,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> StageResponse:
    row = await service.add_stage(session, tenant=tenant, pipeline_id=pipeline_id, stage=payload)
    return StageResponse.model_validate(row)


@router.post("/pipelines/{pipeline_id}/stages/reorder", response_model=list[StageResponse])
async def reorder_stages(
    pipeline_id: uuid.UUID, payload: ReorderStagesRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> list[StageResponse]:
    rows = await service.reorder_stages(
        session, tenant=tenant, pipeline_id=pipeline_id, stage_ids=payload.stage_ids
    )
    return [StageResponse.model_validate(s) for s in rows]


@router.delete("/pipelines/{pipeline_id}/stages/{stage_id}", status_code=204)
async def delete_stage(
    pipeline_id: uuid.UUID, stage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> None:
    await service.delete_stage(session, tenant=tenant, pipeline_id=pipeline_id, stage_id=stage_id)


# ---- analytics ----
@router.get("/analytics", response_model=PipelineAnalytics)
async def analytics(
    pipeline_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> PipelineAnalytics:
    return await service.analytics(session, tenant=tenant, pipeline_id=pipeline_id)


# ---- deals ----
@router.get("/deals", response_model=DealList)
async def list_deals(
    pipeline_id: uuid.UUID | None = Query(default=None),
    stage_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_user_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> DealList:
    rows, total = await service.list_deals(
        session, tenant=tenant, pipeline_id=pipeline_id, stage_id=stage_id,
        deal_status=status, owner_user_id=owner_user_id, q=q, limit=limit, offset=offset,
    )
    return DealList(items=[DealResponse.model_validate(d) for d in rows], total=total)


@router.post("/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    payload: DealCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> DealResponse:
    return DealResponse.model_validate(await service.create_deal(session, tenant=tenant, payload=payload))


@router.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> DealResponse:
    return DealResponse.model_validate(
        await service._owned_deal(session, tenant=tenant, deal_id=deal_id)
    )


@router.patch("/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: uuid.UUID, payload: DealUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> DealResponse:
    return DealResponse.model_validate(
        await service.update_deal(session, tenant=tenant, deal_id=deal_id, payload=payload)
    )


@router.delete("/deals/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> None:
    await service.delete_deal(session, tenant=tenant, deal_id=deal_id)


@router.post("/deals/{deal_id}/move", response_model=DealResponse)
async def move_deal(
    deal_id: uuid.UUID, payload: DealMoveRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> DealResponse:
    return DealResponse.model_validate(
        await service.move_deal(
            session, tenant=tenant, deal_id=deal_id, stage_id=payload.stage_id, note=payload.note
        )
    )


@router.post("/deals/{deal_id}/close", response_model=DealResponse)
async def close_deal(
    deal_id: uuid.UUID, payload: DealCloseRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> DealResponse:
    return DealResponse.model_validate(
        await service.close_deal(
            session, tenant=tenant, deal_id=deal_id,
            close_status=payload.status, lost_reason=payload.lost_reason,
        )
    )


@router.post("/deals/{deal_id}/next-action", response_model=DealResponse)
async def deal_next_action(
    deal_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)
) -> DealResponse:
    """Grounded AI next-action for the deal — cached onto the row."""
    return DealResponse.model_validate(
        await service.generate_next_action(session, tenant=tenant, deal_id=deal_id)
    )


@router.get("/deals/{deal_id}/events", response_model=DealEventList)
async def deal_events(
    deal_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> DealEventList:
    rows = await service.deal_events(session, tenant=tenant, deal_id=deal_id)
    return DealEventList(items=[DealEventResponse.model_validate(e) for e in rows])
