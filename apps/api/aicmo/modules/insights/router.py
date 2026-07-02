"""Module 7 — Autonomous Insights HTTP surface.

  GET /insights/feed — the unified, ranked, grouped AI insights feed. Pure
                       aggregation of existing outputs; analytics.view.

Tenant-scoped via require_permission; every underlying read is brand-scoped.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.insights import service
from aicmo.modules.insights.schemas import InsightFeedResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/feed", response_model=InsightFeedResponse)
async def feed(
    category: str | None = Query(default=None),
    min_severity: str | None = Query(
        default=None, pattern="^(critical|high|medium|low)$"
    ),
    channel: str | None = Query(default=None),
    objective: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> InsightFeedResponse:
    """One prioritized feed aggregating decisions, opportunities, learnings,
    performance diagnostics, strategy, and business analysis — deduped, ranked,
    grouped, each explaining why it surfaced and linking back to its module."""
    return await service.build_feed(
        session,
        tenant=tenant,
        category=category,
        min_severity=min_severity,
        channel=channel,
        objective=objective,
    )
