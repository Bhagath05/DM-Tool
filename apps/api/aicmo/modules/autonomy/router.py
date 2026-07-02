"""Module 9 — Autonomy Policy HTTP surface.

  GET /autonomy/policy    — the current (or safe-default) policy. analytics.view.
  PUT /autonomy/policy    — update the policy (admin). settings.manage + audited.
  GET /autonomy/catalog   — governable actions + modes for the UI. analytics.view.
  GET /autonomy/evaluate  — preview a decision for an action. analytics.view.

Tenant-scoped; brand-isolated. Reads never mutate; the evaluate preview never
executes anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.autonomy import service
from aicmo.modules.autonomy.schemas import (
    ActionType,
    AutonomyCatalog,
    AutonomyPolicyConfig,
    AutonomyPolicyUpdate,
    PolicyDecision,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


@router.get("/policy", response_model=AutonomyPolicyConfig)
async def get_policy(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AutonomyPolicyConfig:
    return await service.get_or_default(session, brand_id=tenant.brand_id)


@router.put("/policy", response_model=AutonomyPolicyConfig)
async def put_policy(
    payload: AutonomyPolicyUpdate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> AutonomyPolicyConfig:
    """Update autonomy policy. Admin-only; every change is written to the audit
    log with before/after."""
    return await service.upsert(session, tenant=tenant, payload=payload)


@router.get("/catalog", response_model=AutonomyCatalog)
async def get_catalog(
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> AutonomyCatalog:
    return service.catalog()


@router.get("/evaluate", response_model=PolicyDecision)
async def evaluate(
    action: ActionType,
    amount: float | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> PolicyDecision:
    """Preview: would this action auto-run or require approval under the current
    policy? Read-only — nothing executes."""
    config = await service.get_or_default(session, brand_id=tenant.brand_id)
    return service.evaluate_policy(config, action, amount=amount)
