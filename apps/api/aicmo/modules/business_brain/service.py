"""Business Brain domain service — agent-tool compatible surface.

Future Marketing Agent should call these functions (or thin tool wrappers),
never manipulate tables directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_brain.models import BrainEvidence, BrainIcp, BrainResearchJob
from aicmo.modules.business_brain.research_service import (
    _require_brand,
    get_job,
    job_to_response,
    latest_job_for_kind,
    start_competitor_research,
    start_market_research,
    start_website_research,
)
from aicmo.modules.business_brain.schemas import (
    BrainSummaryResponse,
    CompetitorCandidate,
    CompetitorResearchResponse,
    EvidenceItem,
    EvidenceListResponse,
    MarketResearchResponse,
    MarketSignal,
    ResearchJobResponse,
    ResearchJobStartResponse,
    StartCompetitorResearchRequest,
    StartWebsiteResearchRequest,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext

__all__ = [
    "get_context",
    "get_evidence",
    "get_icp_hypotheses",
    "get_research_job",
    "list_competitors",
    "list_evidence",
    "list_market_signals",
    "research_competitors",
    "research_market",
    "research_website",
]


async def research_website(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartWebsiteResearchRequest,
) -> ResearchJobStartResponse:
    """Tool: research_website"""
    return await start_website_research(session, tenant=tenant, payload=payload)


async def research_competitors(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: StartCompetitorResearchRequest | None = None,
) -> ResearchJobStartResponse:
    """Tool: research_competitors"""
    return await start_competitor_research(
        session,
        tenant=tenant,
        payload=payload or StartCompetitorResearchRequest(),
    )


async def research_market(
    session: AsyncSession,
    *,
    tenant: TenantContext,
) -> ResearchJobStartResponse:
    """Tool: research_market"""
    return await start_market_research(session, tenant=tenant)


async def get_research_job(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    job_id: uuid.UUID,
) -> ResearchJobResponse:
    """Tool: research status"""
    row = await get_job(session, tenant=tenant, job_id=job_id)
    return job_to_response(row)


async def get_evidence(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    kind: str | None = None,
    limit: int = 100,
) -> EvidenceListResponse:
    """Tool: get_evidence"""
    return await list_evidence(session, tenant=tenant, kind=kind, limit=limit)


async def list_evidence(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    kind: str | None = None,
    limit: int = 100,
) -> EvidenceListResponse:
    brand_id = _require_brand(tenant)
    stmt = (
        select(BrainEvidence)
        .where(
            BrainEvidence.brand_id == brand_id,
            BrainEvidence.status == "active",
        )
        .order_by(BrainEvidence.discovered_at.desc())
        .limit(min(limit, 200))
    )
    if kind:
        stmt = stmt.where(BrainEvidence.kind == kind)
    rows = list((await session.scalars(stmt)).all())

    counts: dict[str, int] = {
        "fact": 0,
        "observation": 0,
        "hypothesis": 0,
        "recommendation": 0,
    }
    for r in rows:
        if r.kind in counts:
            counts[r.kind] += 1

    present_categories = {r.category for r in rows}
    unknown = [
        c
        for c in ("business", "audience", "market", "marketing")
        if c not in present_categories
    ]

    items = [
        EvidenceItem(
            id=r.id,
            kind=r.kind,  # type: ignore[arg-type]
            category=r.category,  # type: ignore[arg-type]
            claim=r.claim,
            confidence=r.confidence,
            status=r.status,
            claim_key=r.claim_key,
            superseded_by_id=r.superseded_by_id,
            source_url=r.source_url,
            source_type=r.source_type,
            snippet=r.snippet,
            research_job_id=r.research_job_id,
            discovered_at=r.discovered_at,
            retrieved_at=r.discovered_at,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return EvidenceListResponse(
        items=items,
        known_count=len(items),
        unknown_categories=unknown,
    )


async def list_competitors(
    session: AsyncSession, *, tenant: TenantContext
) -> CompetitorResearchResponse:
    """Tool: get competitors (from latest competitor research job)."""
    brand_id = _require_brand(tenant)
    job = await latest_job_for_kind(session, brand_id=brand_id, kind="competitor")
    if job is None:
        return CompetitorResearchResponse(
            status="INSUFFICIENT_EVIDENCE",
            message=(
                "No competitor research yet. Provide competitor website URLs "
                "to research — we do not invent competitor companies."
            ),
            candidates=[],
        )
    job_resp = job_to_response(job)
    if job.status in ("queued", "running"):
        return CompetitorResearchResponse(
            status=job.status,  # type: ignore[arg-type]
            message="Competitor research is in progress.",
            latest_job=job_resp,
            candidates=[],
        )
    if job.status == "failed":
        cat = job.error_category or "RESEARCH_FAILED"
        status_map = {
            "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "PROVIDER_UNAVAILABLE": "PROVIDER_UNAVAILABLE",
        }
        return CompetitorResearchResponse(
            status=status_map.get(cat, "failed"),  # type: ignore[arg-type]
            message=job.error_message,
            latest_job=job_resp,
            candidates=[],
        )
    summary = job.result_summary if isinstance(job.result_summary, dict) else {}
    raw = list(summary.get("candidates") or [])
    candidates: list[CompetitorCandidate] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        try:
            candidates.append(CompetitorCandidate.model_validate(c))
        except Exception:
            continue
    return CompetitorResearchResponse(
        status="ok" if candidates else "INSUFFICIENT_EVIDENCE",
        message=None
        if candidates
        else "Research finished but no competitor candidates were supported.",
        latest_job=job_resp,
        candidates=candidates,
    )


async def list_market_signals(
    session: AsyncSession, *, tenant: TenantContext
) -> MarketResearchResponse:
    """Tool: get market signals (from latest market research job)."""
    brand_id = _require_brand(tenant)
    job = await latest_job_for_kind(session, brand_id=brand_id, kind="market")
    if job is None:
        return MarketResearchResponse(
            status="INSUFFICIENT_EVIDENCE",
            message=(
                "No market research yet. Run website research first so market "
                "signals can be derived from evidence."
            ),
            signals=[],
        )
    job_resp = job_to_response(job)
    if job.status in ("queued", "running"):
        return MarketResearchResponse(
            status=job.status,  # type: ignore[arg-type]
            message="Market research is in progress.",
            latest_job=job_resp,
            signals=[],
        )
    if job.status == "failed":
        cat = job.error_category or "RESEARCH_FAILED"
        status_map = {
            "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "PROVIDER_UNAVAILABLE": "PROVIDER_UNAVAILABLE",
        }
        return MarketResearchResponse(
            status=status_map.get(cat, "failed"),  # type: ignore[arg-type]
            message=job.error_message,
            latest_job=job_resp,
            signals=[],
        )
    summary = job.result_summary if isinstance(job.result_summary, dict) else {}
    raw = list(summary.get("signals") or [])
    signals: list[MarketSignal] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        try:
            signals.append(MarketSignal.model_validate(s))
        except Exception:
            continue
    return MarketResearchResponse(
        status="ok" if signals else "INSUFFICIENT_EVIDENCE",
        message=None if signals else "No market signals could be derived.",
        latest_job=job_resp,
        signals=signals,
    )


async def get_icp_hypotheses(session: AsyncSession, *, tenant: TenantContext):
    """Tool: get_icp_hypotheses"""
    from aicmo.modules.business_brain import icp_service

    return await icp_service.list_icps(session, tenant=tenant)


async def get_context(
    session: AsyncSession, *, tenant: TenantContext
) -> BrainSummaryResponse:
    """Tool: get_business_context — bounded structured evidence, not a prompt blob."""
    brand_id = _require_brand(tenant)
    profile = await onboarding_service.get_profile_or_none(session, brand_id)

    known: list[str] = []
    unknown: list[str] = []
    if profile is None:
        unknown.extend(
            [
                "business_name",
                "website",
                "industry",
                "products_services",
                "target_audience",
                "positioning",
            ]
        )
    else:
        for label, value in (
            ("business_name", profile.business_name),
            ("website", profile.website),
            ("industry", profile.industry),
            ("target_audience", profile.target_audience),
            ("brand_tone", profile.brand_tone),
        ):
            if value and str(value).strip():
                known.append(label)
            else:
                unknown.append(label)
        products = list(profile.products or []) + list(profile.services or [])
        if products:
            known.append("products_services")
        else:
            unknown.append("products_services")

    evidence = await list_evidence(session, tenant=tenant, limit=200)
    for cat in evidence.unknown_categories:
        key = f"evidence:{cat}"
        if key not in unknown:
            unknown.append(key)
    cats_with_ground = {
        e.category for e in evidence.items if e.kind in ("fact", "observation")
    }
    for cat in ("business", "audience", "market", "marketing"):
        key = f"evidence:{cat}"
        if cat in cats_with_ground:
            if key not in known:
                known.append(key)
            if key in unknown:
                unknown.remove(key)

    latest = await session.scalar(
        select(BrainResearchJob)
        .where(BrainResearchJob.brand_id == brand_id)
        .order_by(BrainResearchJob.created_at.desc())
        .limit(1)
    )
    website_job = await latest_job_for_kind(session, brand_id=brand_id, kind="website")
    competitor_job = await latest_job_for_kind(
        session, brand_id=brand_id, kind="competitor"
    )
    market_job = await latest_job_for_kind(session, brand_id=brand_id, kind="market")

    icp_count = len(
        list(
            (
                await session.scalars(
                    select(BrainIcp.id).where(
                        BrainIcp.brand_id == brand_id,
                        BrainIcp.status.in_(("hypothesis", "accepted")),
                    )
                )
            ).all()
        )
    )

    competitors = await list_competitors(session, tenant=tenant)
    market = await list_market_signals(session, tenant=tenant)

    counts = {"fact": 0, "observation": 0, "hypothesis": 0, "recommendation": 0}
    for e in evidence.items:
        if e.kind in counts:
            counts[e.kind] += 1

    limitations = [
        "Competitor candidates are not verified companies unless sources support them.",
        "Market signals never include fabricated size, share, or growth metrics.",
        "LLM interpretations remain hypotheses.",
        "No people, leads, or outreach data in Business Brain Phase 2.",
    ]
    if competitors.status == "INSUFFICIENT_EVIDENCE":
        limitations.append("Competitor research has insufficient evidence.")
    if market.status == "INSUFFICIENT_EVIDENCE":
        limitations.append("Market research has insufficient evidence.")

    return BrainSummaryResponse(
        profile_present=profile is not None,
        business_name=getattr(profile, "business_name", None) if profile else None,
        website=getattr(profile, "website", None) if profile else None,
        industry=getattr(profile, "industry", None) if profile else None,
        known=known,
        unknown=unknown,
        evidence_counts=counts,
        latest_job=job_to_response(latest) if latest else None,
        latest_website_job=job_to_response(website_job) if website_job else None,
        latest_competitor_job=job_to_response(competitor_job) if competitor_job else None,
        latest_market_job=job_to_response(market_job) if market_job else None,
        icp_count=icp_count,
        competitor_candidate_count=len(competitors.candidates),
        market_signal_count=len(market.signals),
        limitations=limitations,
    )
