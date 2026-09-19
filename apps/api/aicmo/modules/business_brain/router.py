"""HTTP surface for Business Brain.

Permission: settings.manage for research/ICP generate (same as Brand Brain /
discovery setup). Polls and reads require an active tenant only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.business_brain import icp_service, research_service, service
from aicmo.modules.business_brain.schemas import (
    BrainSummaryResponse,
    CompetitorResearchResponse,
    EvidenceListResponse,
    IcpGenerateResponse,
    IcpListResponse,
    MarketResearchResponse,
    ResearchJobResponse,
    ResearchJobStartResponse,
    StartCompetitorResearchRequest,
    StartWebsiteResearchRequest,
)
from aicmo.queue.deps import get_arq_pool
from aicmo.queue.enqueue import enqueue_tenant_job
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

router = APIRouter(prefix="/business-brain", tags=["business-brain"])

_RequireSetup = require_permission("settings.manage")


@router.get("", response_model=BrainSummaryResponse)
async def get_brain_summary(
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> BrainSummaryResponse:
    return await service.get_context(session, tenant=tenant)


@router.get("/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    kind: str | None = Query(default=None),
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> EvidenceListResponse:
    return await service.list_evidence(session, tenant=tenant, kind=kind)


@router.post("/research/website", response_model=ResearchJobStartResponse, status_code=202)
async def start_website_research(
    payload: StartWebsiteResearchRequest,
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> ResearchJobStartResponse:
    result = await research_service.start_website_research(
        session, tenant=tenant, payload=payload
    )
    await _enqueue_or_background(result, background, tenant, pool)
    return result


@router.post(
    "/research/competitors",
    response_model=ResearchJobStartResponse,
    status_code=202,
)
async def start_competitor_research(
    payload: StartCompetitorResearchRequest,
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> ResearchJobStartResponse:
    result = await research_service.start_competitor_research(
        session,
        tenant=tenant,
        payload=payload,
    )
    await _enqueue_or_background(result, background, tenant, pool)
    return result


@router.post("/research/market", response_model=ResearchJobStartResponse, status_code=202)
async def start_market_research(
    background: BackgroundTasks,
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> ResearchJobStartResponse:
    result = await research_service.start_market_research(session, tenant=tenant)
    await _enqueue_or_background(result, background, tenant, pool)
    return result


@router.get("/research/{job_id}", response_model=ResearchJobResponse)
async def get_research_job(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> ResearchJobResponse:
    return await service.get_research_job(session, tenant=tenant, job_id=job_id)


@router.get("/competitors", response_model=CompetitorResearchResponse)
async def get_competitors(
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> CompetitorResearchResponse:
    return await service.list_competitors(session, tenant=tenant)


@router.get("/market", response_model=MarketResearchResponse)
async def get_market(
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> MarketResearchResponse:
    return await service.list_market_signals(session, tenant=tenant)


@router.get("/icps", response_model=IcpListResponse)
async def list_icps(
    tenant: TenantContext = Depends(require_tenant()),
    session: AsyncSession = Depends(get_db),
) -> IcpListResponse:
    return await icp_service.list_icps(session, tenant=tenant)


@router.post("/icps/generate", response_model=IcpGenerateResponse)
async def generate_icps(
    tenant: TenantContext = Depends(_RequireSetup),
    session: AsyncSession = Depends(get_db),
) -> IcpGenerateResponse:
    return await icp_service.generate_icps(session, tenant=tenant)


async def _enqueue_or_background(
    result: ResearchJobStartResponse,
    background: BackgroundTasks,
    tenant: TenantContext,
    pool,
) -> None:
    if result.reused_existing:
        return
    job = await enqueue_tenant_job(
        pool,
        "run_business_brain_research",
        str(result.id),
        tenant=tenant,
    )
    if job is None:
        background.add_task(_run_job_background, str(result.id), tenant)


async def _run_job_background(job_id: str, tenant: TenantContext) -> None:
    from aicmo.db.session import SessionLocal

    async with SessionLocal() as session:
        await research_service.execute_research_job(
            session,
            job_id=uuid.UUID(job_id),
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,  # type: ignore[arg-type]
        )
