"""Org-wide Audit Log HTTP surface (Phase 6.6 Slice 4).

    GET /api/v1/orgs/{org_id}/audit   — filtered, newest-first audit trail

Gated on `organization.manage` (owners + admins) — the same floor as the
rest of the org-settings surface. Read-only; the write path is unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.audit import service
from aicmo.modules.audit.schemas import AuditEventList
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/orgs", tags=["audit"])


@router.get("/{org_id}/audit", response_model=AuditEventList)
async def list_org_audit(
    org_id: uuid.UUID,
    action: list[str] | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    target_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    tenant: TenantContext = Depends(require_permission("organization.manage", brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> AuditEventList:
    if tenant.organization_id != org_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant context does not match URL organization",
        )
    items = await service.list_events(
        session,
        organization_id=org_id,
        actions=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        since=since,
        until=until,
        search=search,
        limit=limit,
    )
    actions = await service.distinct_actions(session, organization_id=org_id)
    return AuditEventList(items=items, actions=actions)
