"""Research job lifecycle — website, competitor, and market kinds."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_brain.ingestion import ingest_research_result
from aicmo.modules.business_brain.models import BrainEvidence, BrainResearchJob
from aicmo.modules.business_brain.providers.local_competitor import (
    get_competitor_research_provider,
)
from aicmo.modules.business_brain.providers.local_market import (
    get_market_research_provider,
)
from aicmo.modules.business_brain.providers.local_website import (
    get_website_research_provider,
)
from aicmo.modules.business_brain.schemas import (
    ResearchJobResponse,
    ResearchJobStartResponse,
    ResearchResult,
    StartCompetitorResearchRequest,
    StartWebsiteResearchRequest,
)
from aicmo.modules.discovery.fetcher import DiscoveryFetchError, normalize_url
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Permission decision (documented): reuse settings.manage — same floor as
# Brand Brain / discovery setup mutations. No new RBAC catalog entry.

_KIND_WEBSITE = "website"
_KIND_COMPETITOR = "competitor"
_KIND_MARKET = "market"


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Pick a workspace first, then we can research the business.",
        )
    return tenant.brand_id


def job_to_response(row: BrainResearchJob) -> ResearchJobResponse:
    return ResearchJobResponse(
        id=row.id,
        kind=row.kind,
        input_url=row.input_url,
        normalized_url=row.normalized_url,
        status=row.status,  # type: ignore[arg-type]
        error_category=row.error_category,  # type: ignore[arg-type]
        error_message=row.error_message,
        provider=row.provider,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        source_count=row.source_count,
        evidence_count=row.evidence_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def start_website_research(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartWebsiteResearchRequest,
) -> ResearchJobStartResponse:
    try:
        normalized = normalize_url(payload.website_url)
    except DiscoveryFetchError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return await _start_job(
        session,
        tenant=tenant,
        kind=_KIND_WEBSITE,
        input_url=payload.website_url.strip()[:500],
        normalized_url=normalized[:500],
        result_seed=None,
    )


async def start_competitor_research(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartCompetitorResearchRequest,
) -> ResearchJobStartResponse:
    brand_id = _require_brand(tenant)
    profile = await onboarding_service.get_profile_or_none(session, brand_id)
    website = (getattr(profile, "website", None) or "").strip()
    if website:
        try:
            key = f"competitor:{normalize_url(website)}"
            input_url = website
        except DiscoveryFetchError:
            key = f"competitor:brand:{brand_id}"
            input_url = website
    else:
        key = f"competitor:brand:{brand_id}"
        input_url = "competitor-research"
    seed = {"competitor_urls": list(payload.competitor_urls or [])[:5]}
    return await _start_job(
        session,
        tenant=tenant,
        kind=_KIND_COMPETITOR,
        input_url=input_url[:500],
        normalized_url=key[:500],
        result_seed=seed,
    )


async def start_market_research(
    session: AsyncSession,
    *,
    tenant: TenantContext,
) -> ResearchJobStartResponse:
    brand_id = _require_brand(tenant)
    profile = await onboarding_service.get_profile_or_none(session, brand_id)
    website = (getattr(profile, "website", None) or "").strip()
    if website:
        try:
            key = f"market:{normalize_url(website)}"
            input_url = website
        except DiscoveryFetchError:
            key = f"market:brand:{brand_id}"
            input_url = website
    else:
        key = f"market:brand:{brand_id}"
        input_url = "market-research"
    return await _start_job(
        session,
        tenant=tenant,
        kind=_KIND_MARKET,
        input_url=input_url[:500],
        normalized_url=key[:500],
        result_seed=None,
    )


async def _start_job(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    kind: str,
    input_url: str,
    normalized_url: str,
    result_seed: dict[str, Any] | None,
) -> ResearchJobStartResponse:
    brand_id = _require_brand(tenant)
    existing = await session.scalar(
        select(BrainResearchJob).where(
            BrainResearchJob.brand_id == brand_id,
            BrainResearchJob.kind == kind,
            BrainResearchJob.normalized_url == normalized_url,
            BrainResearchJob.status.in_(("queued", "running")),
        )
    )
    if existing is not None:
        return ResearchJobStartResponse(
            id=existing.id,
            status=existing.status,  # type: ignore[arg-type]
            reused_existing=True,
        )

    row = BrainResearchJob(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        created_by_user_id=tenant.user_uuid,
        kind=kind,
        input_url=input_url,
        normalized_url=normalized_url,
        status="queued",
        result_summary=result_seed,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        winner = await session.scalar(
            select(BrainResearchJob).where(
                BrainResearchJob.brand_id == brand_id,
                BrainResearchJob.kind == kind,
                BrainResearchJob.normalized_url == normalized_url,
                BrainResearchJob.status.in_(("queued", "running")),
            )
        )
        if winner is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A research job is already in progress.",
            ) from None
        return ResearchJobStartResponse(
            id=winner.id,
            status=winner.status,  # type: ignore[arg-type]
            reused_existing=True,
        )

    await session.commit()
    await session.refresh(row)
    return ResearchJobStartResponse(id=row.id, status="queued", reused_existing=False)


async def get_job(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    job_id: uuid.UUID,
) -> BrainResearchJob:
    brand_id = _require_brand(tenant)
    row = await session.get(BrainResearchJob, job_id)
    if row is None or row.brand_id != brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research job not found.")
    return row


async def latest_job_for_kind(
    session: AsyncSession, *, brand_id: uuid.UUID, kind: str
) -> BrainResearchJob | None:
    return await session.scalar(
        select(BrainResearchJob)
        .where(
            BrainResearchJob.brand_id == brand_id,
            BrainResearchJob.kind == kind,
        )
        .order_by(BrainResearchJob.created_at.desc())
        .limit(1)
    )


async def execute_research_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> None:
    """Worker entry — tenant already restored by @tenant_job.

    Claim is atomic: only ``queued → running`` wins. Retries that see
    ``running``/terminal statuses exit without refetching or re-ingesting.
    """
    started = datetime.now(UTC)
    claim = await session.execute(
        update(BrainResearchJob)
        .where(
            BrainResearchJob.id == job_id,
            BrainResearchJob.organization_id == organization_id,
            BrainResearchJob.brand_id == brand_id,
            BrainResearchJob.status == "queued",
        )
        .values(
            status="running",
            started_at=started,
            updated_at=started,
        )
        .returning(
            BrainResearchJob.id,
            BrainResearchJob.normalized_url,
            BrainResearchJob.kind,
            BrainResearchJob.result_summary,
        )
    )
    claimed = claim.one_or_none()
    await session.commit()
    if claimed is None:
        existing = await session.get(BrainResearchJob, job_id)
        if existing is not None and (
            existing.organization_id != organization_id or existing.brand_id != brand_id
        ):
            log.warning("business_brain.job_tenant_mismatch", job_id=str(job_id))
        return

    kind = claimed.kind
    result = await _run_provider(
        session,
        kind=kind,
        brand_id=brand_id,
        normalized_url=claimed.normalized_url,
        result_seed=claimed.result_summary if isinstance(claimed.result_summary, dict) else {},
    )

    row = await session.get(BrainResearchJob, job_id)
    if row is None:
        return
    if row.status != "running":
        return

    finished = datetime.now(UTC)
    row.finished_at = finished
    row.duration_ms = int((finished - started).total_seconds() * 1000)
    row.provider = result.provider
    row.source_count = len(result.sources)
    if result.result_summary is not None:
        row.result_summary = result.result_summary

    if result.status == "failed" or (
        not result.evidence
        and not (result.result_summary or {}).get("candidates")
        and not (result.result_summary or {}).get("signals")
    ):
        row.status = "failed"
        row.error_category = result.error_category or "RESEARCH_FAILED"
        row.error_message = (result.error_message or "Research failed.")[:500]
        row.evidence_count = 0
        await session.commit()
        return

    evidence_rows = await ingest_research_result(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        research_job_id=job_id,
        result=result,
    )
    row.evidence_count = len(evidence_rows)
    if result.status == "partial":
        row.status = "partial"
        row.error_category = result.error_category or "PARTIAL_EVIDENCE"
        row.error_message = result.error_message
    else:
        row.status = "completed"
        row.error_category = None
        row.error_message = None
    await session.commit()


async def _run_provider(
    session: AsyncSession,
    *,
    kind: str,
    brand_id: uuid.UUID,
    normalized_url: str,
    result_seed: dict[str, Any],
) -> ResearchResult:
    if kind == _KIND_WEBSITE:
        # Strip any accidental prefix; website jobs store the real URL.
        url = normalized_url
        provider = get_website_research_provider()
        return await provider.research(url=url)

    profile = await onboarding_service.get_profile_or_none(session, brand_id)
    website = (getattr(profile, "website", None) or None) if profile else None
    industry = (getattr(profile, "industry", None) or None) if profile else None
    grounded = list(
        (
            await session.scalars(
                select(BrainEvidence.claim).where(
                    BrainEvidence.brand_id == brand_id,
                    BrainEvidence.status == "active",
                    BrainEvidence.kind.in_(("fact", "observation")),
                ).limit(40)
            )
        ).all()
    )

    if kind == _KIND_COMPETITOR:
        urls = list(result_seed.get("competitor_urls") or [])
        provider = get_competitor_research_provider()
        return await provider.research_competitors(
            business_website=website,
            grounded_claims=[str(c) for c in grounded],
            competitor_urls=[str(u) for u in urls],
        )

    if kind == _KIND_MARKET:
        provider = get_market_research_provider()
        return await provider.research_market(
            business_website=website,
            industry=str(industry) if industry else None,
            grounded_claims=[str(c) for c in grounded],
        )

    return ResearchResult(
        status="failed",
        error_category="RESEARCH_FAILED",
        error_message=f"Unknown research kind: {kind}",
        provider="unknown",
    )
