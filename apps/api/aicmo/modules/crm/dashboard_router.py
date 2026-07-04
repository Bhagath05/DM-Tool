"""Executive CRM Dashboard HTTP API (Phase 6.5, Slice 6). Mounted under /crm.
Read-only aggregation — tenant-scoped + RBAC (crm.view). Export is audited."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.audit import service as audit_service
from aicmo.modules.crm import dashboard_service as svc
from aicmo.modules.crm.dashboard_schemas import ExecutiveDashboard
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm/dashboard", tags=["crm-dashboard"])

_VIEW = require_permission("crm.view")


@router.get("", response_model=ExecutiveDashboard)
async def dashboard(
    pipeline_id: uuid.UUID | None = Query(default=None),
    owner_user_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ExecutiveDashboard:
    return await svc.executive_dashboard(
        session, tenant=tenant, pipeline_id=pipeline_id, owner_user_id=owner_user_id
    )


@router.get("/export")
async def export_dashboard(
    pipeline_id: uuid.UUID | None = Query(default=None),
    owner_user_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> Response:
    """CSV export of the executive summary + rep leaderboard (audited)."""
    dash = await svc.executive_dashboard(
        session, tenant=tenant, pipeline_id=pipeline_id, owner_user_id=owner_user_id
    )
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action="crm.dashboard_exported", brand_id=tenant.brand_id, target_type="crm",
        metadata={"format": "csv"},
    )
    await session.commit()
    return Response(
        content=svc.to_csv(dash), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=crm-executive-dashboard.csv"},
    )
