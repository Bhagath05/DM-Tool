"""Phase 4 — Operations Engine HTTP surface.

  POST /operations/tick        — drive ONE continuous-loop cycle. SYSTEM endpoint
                                 (cross-tenant), gated by a shared secret; not a
                                 tenant route. This is the swappable driver: an
                                 external scheduler calls it today, the Arq cron
                                 later — both invoke the same `run_operations_cycle`.
  GET  /operations/monitoring  — tenant-scoped latest + recent metric snapshots
                                 for the current brand. analytics.view.

The tick is secured (secret + throttle + audited via OperationsRun) and
idempotent (per-brand cadence), so repeated calls never duplicate work.
"""

from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.operations import goals as goals_mod
from aicmo.modules.operations import monitoring, service
from aicmo.modules.operations.driver import run_operations_cycle
from aicmo.modules.operations.schemas import (
    EventsView,
    GoalCreate,
    GoalList,
    GoalResponse,
    GoalStatusUpdate,
    MonitoringView,
    TickResult,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/operations", tags=["operations"])


def _require_operations_secret(
    x_operations_token: str | None = Header(default=None),
) -> None:
    """Gate the system tick behind the shared secret. Disabled (503) until a
    secret is configured, so the loop can't be driven by default."""
    secret = get_settings().operations_tick_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operations loop is disabled — no operations secret configured.",
        )
    if not x_operations_token or not hmac.compare_digest(x_operations_token, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing operations token.",
        )


@router.post("/tick", response_model=TickResult)
async def tick(
    _: None = Depends(_require_operations_secret),
    session: AsyncSession = Depends(get_db),
) -> TickResult:
    """Run one observe→(detect→decide) cycle across all active brands. Secret-
    gated, throttled, idempotent. Nothing executes — the cycle observes and
    queues; execution stays behind the Autonomy Policy."""
    return await run_operations_cycle(session, trigger="api")


@router.get("/monitoring", response_model=MonitoringView)
async def get_monitoring(
    history: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> MonitoringView:
    return await service.monitoring_view(
        session, brand_id=tenant.brand_id, history=history
    )


@router.get("/events", response_model=EventsView)
async def events(
    only_open: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> EventsView:
    """Meaningful changes the monitoring loop detected for this brand (4.2)."""
    return await service.events_view(
        session, brand_id=tenant.brand_id, only_open=only_open, limit=limit
    )


# ---------------------------------------------------------------------
#  4.3 — Autonomous Goal Engine
# ---------------------------------------------------------------------
@router.get("/goals", response_model=GoalList)
async def list_goals(
    only_active: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> GoalList:
    rows = await goals_mod.list_goals(
        session, brand_id=tenant.brand_id, only_active=only_active
    )
    return GoalList(items=[goals_mod.to_response(r) for r in rows])


@router.post("/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> GoalResponse:
    # Seed the baseline from the latest snapshot so progress starts honestly.
    baseline = 0.0
    if goals_mod.is_measurable(payload.metric):
        snap = await monitoring.latest_snapshot(session, brand_id=tenant.brand_id)
        key = goals_mod.snapshot_key_for(payload.metric)
        if snap is not None and key in (snap.metrics or {}):
            try:
                baseline = float(snap.metrics[key])
            except (TypeError, ValueError):
                baseline = 0.0
    row = await goals_mod.create_goal(
        session,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        title=payload.title,
        metric=payload.metric,
        goal_type=payload.goal_type,
        target_value=payload.target_value,
        timeframe_days=payload.timeframe_days,
        baseline_value=baseline,
    )
    await session.commit()
    return goals_mod.to_response(row)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal_status(
    goal_id: uuid.UUID,
    payload: GoalStatusUpdate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> GoalResponse:
    row = await goals_mod.set_status(
        session, brand_id=tenant.brand_id, goal_id=goal_id, status=payload.status
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found."
        )
    await session.commit()
    return goals_mod.to_response(row)
