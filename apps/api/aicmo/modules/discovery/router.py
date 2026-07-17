"""Intelligent Onboarding — Website Discovery HTTP surface.

    POST /discovery/website   → start website discovery (async)
    POST /discovery/scratch   → start from-scratch discovery (async)
    GET  /discovery/{id}      → poll status + reviewable draft
    POST /discovery/{id}/apply→ write the reviewed draft to the Brand Brain

Create/apply need `settings.manage` (same floor as editing the Brand Brain);
polling only needs an active tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.discovery import service
from aicmo.modules.discovery.runner import run_discovery
from aicmo.modules.discovery.schemas import (
    ApplyDiscovery,
    DiscoveryResponse,
    DiscoveryStartResult,
    StartScratchDiscovery,
    StartWebsiteDiscovery,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.analyzer import run_analysis
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

router = APIRouter(prefix="/discovery", tags=["discovery"])

_RequireSetup = require_permission("settings.manage")


@router.post("/website", response_model=DiscoveryStartResult, status_code=202)
async def start_website(
    payload: StartWebsiteDiscovery,
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
) -> DiscoveryStartResult:
    row = await service.create_website(session, tenant=tenant, payload=payload)
    background.add_task(run_discovery, str(row.id))
    return DiscoveryStartResult(id=row.id, status="pending")


@router.post("/scratch", response_model=DiscoveryStartResult, status_code=202)
async def start_scratch(
    payload: StartScratchDiscovery,
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
) -> DiscoveryStartResult:
    row = await service.create_scratch(session, tenant=tenant, payload=payload)
    background.add_task(run_discovery, str(row.id))
    return DiscoveryStartResult(id=row.id, status="pending")


@router.get("/{discovery_id}", response_model=DiscoveryResponse)
async def get_discovery(
    discovery_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> DiscoveryResponse:
    row = await service.get(session, tenant=tenant, discovery_id=discovery_id)
    return service._to_response(row)


@router.post("/{discovery_id}/apply", response_model=BusinessProfileResponse)
async def apply_discovery(
    discovery_id: uuid.UUID,
    payload: ApplyDiscovery,
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
) -> BusinessProfileResponse:
    reanalyze = await service.apply(
        session, tenant=tenant, discovery_id=discovery_id, payload=payload
    )
    profile = await onboarding_service.require_profile(session, tenant.brand_id)
    response = onboarding_service._to_response(profile)
    if reanalyze:
        background.add_task(run_analysis, str(response.id), response)
    return response
