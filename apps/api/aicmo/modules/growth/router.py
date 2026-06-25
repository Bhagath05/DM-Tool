"""Growth HTTP surface — the outcome layer (Law 1).

Flag-gated behind `studio_enabled` (default false → 409), so the outcome
intake ships dark with the rest of CS1. Brand-scoped + RBAC (`growth.*`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.growth import campaign as campaign_builder
from aicmo.modules.growth import service as growth_service
from aicmo.modules.growth.schemas import (
    BuiltAssetOut,
    CampaignBuildResponse,
    CampaignStrategyOut,
    CreateObjectiveRequest,
    ObjectiveKindOut,
    ObjectiveList,
    ObjectiveResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/growth", tags=["growth"])

_RequireRead = require_permission("growth.read")
_RequireCreate = require_permission("growth.create")
_RequireCompose = require_permission("content.create")


def _require_enabled() -> None:
    if not get_settings().studio_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The Growth / Creative Studio isn't enabled yet.",
        )


@router.get("/objective-kinds", response_model=list[ObjectiveKindOut])
async def list_objective_kinds(
    _tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> list[ObjectiveKindOut]:
    _require_enabled()
    rows = await growth_service.list_objective_kinds(session)
    return [ObjectiveKindOut.model_validate(r) for r in rows]


@router.post("/objectives", response_model=ObjectiveResponse, status_code=status.HTTP_201_CREATED)
async def create_objective(
    payload: CreateObjectiveRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> ObjectiveResponse:
    _require_enabled()
    try:
        obj = await growth_service.create_objective(session, tenant=tenant, payload=payload)
    except growth_service.UnknownObjectiveKind:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown objective kind.")
    except growth_service.MissingBrand:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a brand first.")
    await session.commit()
    return ObjectiveResponse.model_validate(obj)


@router.get("/objectives", response_model=ObjectiveList)
async def list_objectives(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> ObjectiveList:
    _require_enabled()
    rows = await growth_service.list_objectives(session, tenant=tenant)
    return ObjectiveList(items=[ObjectiveResponse.model_validate(r) for r in rows])


@router.get("/objectives/{objective_id}", response_model=ObjectiveResponse)
async def get_objective(
    objective_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> ObjectiveResponse:
    _require_enabled()
    obj = await growth_service.get_objective(session, tenant=tenant, objective_id=objective_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Objective not found.")
    return ObjectiveResponse.model_validate(obj)


@router.post(
    "/objectives/{objective_id}/build-campaign",
    response_model=CampaignBuildResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_campaign(
    objective_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireCompose),
    session: AsyncSession = Depends(get_db),
) -> CampaignBuildResponse:
    """Turn an objective into a strategy + a set of editable creatives
    (poster / carousel / ad / reel). Each asset is a real editable design."""
    _require_enabled()
    objective = await growth_service.get_objective(session, tenant=tenant, objective_id=objective_id)
    if objective is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Objective not found.")
    strategy, built = await campaign_builder.build_campaign(
        session, tenant=tenant, objective=objective
    )
    await session.commit()
    return CampaignBuildResponse(
        objective_id=objective.id,
        strategy=CampaignStrategyOut(
            objective_summary=strategy.objective_summary, audience=strategy.audience,
            hook=strategy.hook, value_prop=strategy.value_prop,
            proof_point=strategy.proof_point, cta_angle=strategy.cta_angle,
            channels=strategy.channels,
        ),
        assets=[
            BuiltAssetOut(
                design_id=b.design.id, name=b.design.name,
                creative_type=b.spec.creative_type, media_type=b.design.media_type,
                aspect=b.spec.aspect, current_revision=b.design.current_revision,
                rationale=b.spec.rationale,
            )
            for b in built
        ],
    )
