"""Campaign Learning Lab API. Post W1-12: brand-scoped + permission-gated."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.learning import service
from aicmo.modules.learning.engine import run_engine
from aicmo.modules.learning.schemas import (
    CampaignExperimentList,
    CampaignExperimentResponse,
    ExperimentProvenance,
    ExperimentResultList,
    LearningEventList,
    LearningEventResponse,
    LearningRunRequest,
    LearningRunResult,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/experiments", response_model=CampaignExperimentList)
async def list_experiments(
    status_filter: str | None = Query(default=None, alias="status"),
    platform: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> CampaignExperimentList:
    items = await service.list_experiments(
        session,
        brand_id=tenant.brand_id,
        status=status_filter,
        platform=platform,
        limit=limit,
    )
    return CampaignExperimentList(items=items)


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=ExperimentResultList,
)
async def list_results(
    experiment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> ExperimentResultList:
    exp_rows = await service.list_experiments(
        session, brand_id=tenant.brand_id, limit=200
    )
    if not any(e.id == experiment_id for e in exp_rows):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment not found.",
        )
    items = await service.list_results_for_experiment(
        session, experiment_id=experiment_id
    )
    return ExperimentResultList(items=items)


@router.post(
    "/experiments/{experiment_id}/archive",
    response_model=CampaignExperimentResponse,
)
async def archive_experiment(
    experiment_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> CampaignExperimentResponse:
    row = await service.archive_experiment(
        session, brand_id=tenant.brand_id, experiment_id=experiment_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment not found.",
        )
    await session.commit()
    return row


@router.get("/events", response_model=LearningEventList)
async def list_events(
    variable: str | None = Query(default=None),
    only_active: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> LearningEventList:
    items = await service.list_learning_events(
        session,
        brand_id=tenant.brand_id,
        variable=variable,
        only_active=only_active,
        limit=limit,
    )
    return LearningEventList(items=items)


@router.post(
    "/events/{event_id}/archive",
    response_model=LearningEventResponse,
)
async def archive_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> LearningEventResponse:
    row = await service.archive_learning_event(
        session, brand_id=tenant.brand_id, event_id=event_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning event not found.",
        )
    await session.commit()
    return row


@router.get(
    "/provenance/{source_asset_id}",
    response_model=ExperimentProvenance,
)
async def provenance(
    source_asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> ExperimentProvenance:
    prov = await service.provenance_for_asset(
        session, brand_id=tenant.brand_id, source_asset_id=source_asset_id
    )
    if prov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No experiment recorded for this asset — likely generated before "
                "the Learning Lab was enabled."
            ),
        )
    return prov


@router.post("/analyze", response_model=LearningRunResult)
async def analyze(
    payload: LearningRunRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> LearningRunResult:
    return await run_engine(
        session,
        tenant=tenant,
        variable=payload.variable,
    )
