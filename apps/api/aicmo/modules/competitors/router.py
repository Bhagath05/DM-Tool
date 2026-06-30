"""Competitor intelligence HTTP surface.

  GET /competitors/analysis  — AI analysis of the competitors in the
                               brand's business profile. Tenant-scoped,
                               gated on `analytics.view` (same as the
                               other Market Intelligence reads). One LLM
                               call per request; the frontend caches.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.competitors import service
from aicmo.modules.competitors.schemas import CompetitorAnalysisResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.get("/analysis", response_model=CompetitorAnalysisResponse)
async def get_analysis(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> CompetitorAnalysisResponse:
    try:
        return await service.analyze_competitors(session, brand_id=tenant.brand_id)
    except service.ProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete your business profile before analysing competitors.",
        ) from None
    except service.NoCompetitors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Add the competitors you want to track in your business "
                "profile, then run the analysis."
            ),
        ) from None
