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

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.operations import service
from aicmo.modules.operations.driver import run_operations_cycle
from aicmo.modules.operations.schemas import MonitoringView, TickResult
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
async def monitoring(
    history: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> MonitoringView:
    return await service.monitoring_view(
        session, brand_id=tenant.brand_id, history=history
    )
