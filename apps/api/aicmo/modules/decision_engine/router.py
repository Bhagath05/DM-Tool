"""Decision Engine HTTP surface.

  GET /decisions — structured, evidence-grounded decisions for this brand.

Tenant-scoped, gated on analytics.view (a read/reasoning surface). Gathers real
signals + one LLM call; the frontend caches. Nothing executes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.decision_engine import service
from aicmo.modules.decision_engine.schemas import DecisionReportResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/decisions", tags=["decision-engine"])


@router.get("", response_model=DecisionReportResponse)
async def get_decisions(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> DecisionReportResponse:
    return await service.decide(session, tenant=tenant)
