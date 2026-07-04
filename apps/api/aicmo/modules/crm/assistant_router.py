"""AI Sales Assistant HTTP API (Phase 6.5, Slice 5). Mounted under /crm.
Tenant-scoped + RBAC (crm.view read / crm.manage generate) + audited +
ownership-validated. Every response carries the evidence contract; thin records
return the honest "Not enough evidence." insight."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.crm import assistant_service as svc
from aicmo.modules.crm.assistant_schemas import (
    GenerateInsightRequest,
    InsightList,
    InsightResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm/insights", tags=["crm-assistant"])

_VIEW = require_permission("crm.view")
_MANAGE = require_permission("crm.manage")


@router.get("", response_model=InsightList)
async def list_insights(
    subject_type: str | None = Query(default=None),
    subject_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> InsightList:
    rows = await svc.list_insights(
        session, tenant=tenant, subject_type=subject_type, subject_id=subject_id, limit=limit
    )
    return InsightList(items=[InsightResponse.model_validate(r) for r in rows])


@router.post("/{subject_type}/{subject_id}", response_model=InsightResponse)
async def generate_insight(
    subject_type: str, subject_id: uuid.UUID,
    payload: GenerateInsightRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> InsightResponse:
    """Generate (or return a fresh cached) grounded insight for a CRM record.
    subject_type ∈ lead|deal|contact|company|task|email."""
    row = await svc.generate(
        session, tenant=tenant, subject_type=subject_type, subject_id=subject_id,
        kind=payload.kind, force=payload.force,
    )
    return InsightResponse.model_validate(row)
