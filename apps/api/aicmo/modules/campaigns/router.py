from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.campaigns import service
from aicmo.modules.campaigns.schemas import (
    CampaignPlanList,
    CampaignPlanResponse,
    GenerateCampaignRequest,
    UpdateCampaignRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post(
    "/generate",
    response_model=CampaignPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_campaign(
    payload: GenerateCampaignRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("campaign.create")),
) -> CampaignPlanResponse:
    return await service.generate(session, tenant=tenant, payload=payload)


@router.get("", response_model=CampaignPlanList)
async def list_campaigns(
    saved_only: bool = Query(default=False),
    campaign_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> CampaignPlanList:
    items = await service.list_campaigns(
        session,
        tenant=tenant,
        saved_only=saved_only,
        campaign_type=campaign_type,
        limit=limit,
    )
    return CampaignPlanList(items=items)


@router.get("/{campaign_id}", response_model=CampaignPlanResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> CampaignPlanResponse:
    return await service.get_one(
        session, tenant=tenant, campaign_id=campaign_id
    )


@router.patch("/{campaign_id}", response_model=CampaignPlanResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: UpdateCampaignRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("campaign.edit")),
) -> CampaignPlanResponse:
    return await service.set_saved(
        session,
        tenant=tenant,
        campaign_id=campaign_id,
        is_saved=payload.is_saved,
    )


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("campaign.delete")),
) -> None:
    await service.delete_campaign(
        session, tenant=tenant, campaign_id=campaign_id
    )
