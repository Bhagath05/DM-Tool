"""Module 8 — Agent Orchestrator HTTP surface.

  GET /orchestrator/plan — the AI employee's coordinated next-action plan across
                           the whole lifecycle. Deterministic; analytics.view.

Tenant-scoped; every underlying read is brand-scoped. Nothing executes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.orchestrator import service
from aicmo.modules.orchestrator.schemas import OrchestratorPlan
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/plan", response_model=OrchestratorPlan)
async def plan(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> OrchestratorPlan:
    """Assess where this brand is in the autonomous lifecycle and recommend the
    single next best action — plus the full stage map. Human-approval-gated;
    the orchestrator never runs or publishes anything itself."""
    return await service.build_plan(session, tenant=tenant)
