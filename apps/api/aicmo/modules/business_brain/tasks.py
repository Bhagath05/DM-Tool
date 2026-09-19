"""Arq jobs for Business Brain research (website / competitor / market)."""

from __future__ import annotations

import uuid

import structlog

from aicmo.modules.business_brain import research_service
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope

log = structlog.get_logger()


async def _execute(session, tenant: TenantEnvelope, job_id: str) -> dict:
    org = tenant.org_uuid()
    brand = tenant.brand_uuid()
    if brand is None:
        log.warning("business_brain.job_missing_brand", job_id=job_id)
        return {"status": "missing_brand"}
    await research_service.execute_research_job(
        session,
        job_id=uuid.UUID(job_id),
        organization_id=org,
        brand_id=brand,
    )
    return {"status": "ok", "job_id": job_id}


@tenant_job
async def run_business_brain_research(
    ctx, session, tenant: TenantEnvelope, job_id: str
) -> dict:
    """Execute one research job (any kind) under restored tenant scope."""
    return await _execute(session, tenant, job_id)


@tenant_job
async def run_business_brain_website_research(
    ctx, session, tenant: TenantEnvelope, job_id: str
) -> dict:
    """Phase 1 back-compat job name — same executor."""
    return await _execute(session, tenant, job_id)
