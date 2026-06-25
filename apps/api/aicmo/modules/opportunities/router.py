"""Opportunity Center API surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.opportunities.center import build_opportunity_center
from aicmo.modules.opportunities.schemas import OpportunityCenterReport
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=OpportunityCenterReport)
async def get_opportunity_center(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> OpportunityCenterReport:
    """Phase 6 — Opportunity Center.

    Single LLM call per request. Returns the strategist's content + ad
    opportunities for this week, each carrying the full Constitution
    contract + a generator deep-link.

    409 when business onboarding hasn't been completed — every
    opportunity depends on stage + audience + channel signals from the
    profile.
    """
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before using the Opportunity Center",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)
    return await build_opportunity_center(session, profile=profile, tenant=tenant)
