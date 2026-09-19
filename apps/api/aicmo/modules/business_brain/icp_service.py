"""ICP foundation — evidence-backed WHO hypotheses only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_brain.models import BrainEvidence, BrainIcp, BrainIcpEvidence
from aicmo.modules.business_brain.research_service import _require_brand
from aicmo.modules.business_brain.schemas import IcpGenerateResponse, IcpItem, IcpListResponse
from aicmo.tenancy.context import TenantContext

# Minimum grounded claims before we attempt ICP hypotheses.
_MIN_GROUNDED = 2


def _icp_to_item(icp: BrainIcp, evidence_ids: list[uuid.UUID]) -> IcpItem:
    return IcpItem(
        id=icp.id,
        name=icp.name,
        description=icp.description,
        industries=list(icp.industries or []),
        company_size=icp.company_size,
        geography=list(icp.geography or []),
        buyer_roles=list(icp.buyer_roles or []),
        pain_points=list(icp.pain_points or []),
        buying_signals=list(icp.buying_signals or []),
        exclusions=list(icp.exclusions or []),
        confidence=icp.confidence,
        status=icp.status,  # type: ignore[arg-type]
        evidence_ids=evidence_ids,
        created_at=icp.created_at,
    )


async def list_icps(
    session: AsyncSession, *, tenant: TenantContext
) -> IcpListResponse:
    brand_id = _require_brand(tenant)
    rows = list(
        (
            await session.scalars(
                select(BrainIcp)
                .where(
                    BrainIcp.brand_id == brand_id,
                    BrainIcp.status.in_(("hypothesis", "accepted")),
                )
                .order_by(BrainIcp.created_at.desc())
                .limit(50)
            )
        ).all()
    )
    if not rows:
        grounded = await _grounded_count(session, brand_id=brand_id)
        if grounded < _MIN_GROUNDED:
            return IcpListResponse(
                items=[],
                status="INSUFFICIENT_EVIDENCE",
                message=(
                    "Not enough website facts/observations yet to propose ICPs. "
                    "Run business research first."
                ),
            )
        return IcpListResponse(items=[], status="ok", message="No ICP hypotheses yet.")

    items: list[IcpItem] = []
    for icp in rows:
        eids = list(
            (
                await session.scalars(
                    select(BrainIcpEvidence.evidence_id).where(
                        BrainIcpEvidence.icp_id == icp.id,
                        BrainIcpEvidence.brand_id == brand_id,
                    )
                )
            ).all()
        )
        items.append(_icp_to_item(icp, eids))
    return IcpListResponse(items=items, status="ok")


async def generate_icps(
    session: AsyncSession, *, tenant: TenantContext
) -> IcpGenerateResponse:
    """Create ICP hypotheses only from existing FACT/OBSERVATION evidence."""
    brand_id = _require_brand(tenant)
    grounded = list(
        (
            await session.scalars(
                select(BrainEvidence)
                .where(
                    BrainEvidence.brand_id == brand_id,
                    BrainEvidence.status == "active",
                    BrainEvidence.kind.in_(("fact", "observation")),
                )
                .order_by(BrainEvidence.created_at.desc())
                .limit(40)
            )
        ).all()
    )
    if len(grounded) < _MIN_GROUNDED:
        return IcpGenerateResponse(
            items=[],
            status="INSUFFICIENT_EVIDENCE",
            message=(
                "Need at least two facts/observations before generating ICP "
                "hypotheses. No fabricated ICPs were created."
            ),
        )

    audience_bits = [
        e for e in grounded if e.category in ("audience", "business", "market")
    ]
    if not audience_bits:
        audience_bits = grounded[:5]

    # Deterministic, evidence-backed hypothesis — not a fake company list.
    claim_summary = "; ".join(e.claim[:120] for e in audience_bits[:4])
    icp = BrainIcp(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        name="Primary audience hypothesis",
        description=(
            "Hypothesis derived from website evidence only: "
            f"{claim_summary}. Validate before treating as fact."
        )[:2000],
        industries=[],
        company_size=None,
        geography=[],
        buyer_roles=[],
        pain_points=[],
        buying_signals=[],
        exclusions=[],
        confidence=min(55, max(30, int(sum(e.confidence for e in audience_bits) / len(audience_bits)))),
        status="hypothesis",
        research_job_id=audience_bits[0].research_job_id,
    )
    session.add(icp)
    await session.flush()

    evidence_ids: list[uuid.UUID] = []
    for e in audience_bits[:8]:
        session.add(
            BrainIcpEvidence(
                organization_id=tenant.organization_id,
                brand_id=brand_id,
                icp_id=icp.id,
                evidence_id=e.id,
            )
        )
        evidence_ids.append(e.id)
    await session.commit()
    await session.refresh(icp)

    return IcpGenerateResponse(
        items=[_icp_to_item(icp, evidence_ids)],
        status="ok",
        message="ICP marked as hypothesis — not a verified fact.",
    )


async def _grounded_count(session: AsyncSession, *, brand_id: uuid.UUID) -> int:
    rows = (
        await session.scalars(
            select(BrainEvidence.id).where(
                BrainEvidence.brand_id == brand_id,
                BrainEvidence.status == "active",
                BrainEvidence.kind.in_(("fact", "observation")),
            )
        )
    ).all()
    return len(list(rows))
