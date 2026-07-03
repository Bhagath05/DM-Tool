"""Phase 6.3 — AI creative brief HTTP surface.

Mounted under /creative. Tenant-scoped (service filters by brand) + RBAC-gated
(reuses the same content.read / content.create slugs as the design studio) +
audited. Generation is grounded — see brief_service.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.creative import brief_service
from aicmo.modules.creative.brief_schemas import (
    CreativeBriefList,
    CreativeBriefResponse,
    GenerateBriefRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/creative", tags=["creative-brief"])

_VIEW = require_permission("content.read")
_CREATE = require_permission("content.create")


def _to_response(row) -> CreativeBriefResponse:
    return CreativeBriefResponse.model_validate(row)


@router.post("/brief", response_model=CreativeBriefResponse, status_code=201)
async def generate_brief(
    payload: GenerateBriefRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(_CREATE),
) -> CreativeBriefResponse:
    row = await brief_service.generate_brief(
        session, tenant=tenant, objective=payload.objective,
        campaign_id=payload.campaign_id, content_id=payload.content_id,
        strategy_id=payload.strategy_id,
    )
    return _to_response(row)


@router.get("/briefs", response_model=CreativeBriefList)
async def list_briefs(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(_VIEW),
) -> CreativeBriefList:
    rows = await brief_service.list_briefs(session, tenant=tenant)
    return CreativeBriefList(items=[_to_response(r) for r in rows])


@router.get("/briefs/{brief_id}", response_model=CreativeBriefResponse)
async def get_brief(
    brief_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(_VIEW),
) -> CreativeBriefResponse:
    row = await brief_service.get_brief(session, tenant=tenant, brief_id=brief_id)
    return _to_response(row)
