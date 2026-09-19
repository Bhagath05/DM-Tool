"""Persist ResearchResult into brain_evidence without promoting kinds.

Supports minimal supersession / contradiction:
- Same claim_key + same claim text → skip duplicate (keep existing)
- Same claim_key + different claim → mark prior active as contradicted,
  insert new active row (never silent overwrite)
- Same claim_key + identical meaning already active → no-op
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_brain.models import BrainEvidence
from aicmo.modules.business_brain.schemas import EvidenceCandidate, ResearchResult

_ALLOWED_KINDS = frozenset({"fact", "observation", "hypothesis", "recommendation"})
_ALLOWED_CATEGORIES = frozenset({"business", "audience", "market", "marketing"})


async def ingest_research_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    research_job_id: uuid.UUID,
    result: ResearchResult,
) -> list[BrainEvidence]:
    """Insert evidence rows. Never rewrite hypothesis → fact."""
    rows: list[BrainEvidence] = []
    for cand in result.evidence:
        row = await _ingest_one(
            session,
            cand,
            organization_id=organization_id,
            brand_id=brand_id,
            research_job_id=research_job_id,
            fallback_url=result.final_url,
        )
        if row is not None:
            rows.append(row)
    await session.flush()
    return rows


async def _ingest_one(
    session: AsyncSession,
    cand: EvidenceCandidate,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    research_job_id: uuid.UUID,
    fallback_url: str | None,
) -> BrainEvidence | None:
    kind = cand.kind.strip().lower()
    category = cand.category.strip().lower()
    if kind not in _ALLOWED_KINDS or category not in _ALLOWED_CATEGORIES:
        return None
    claim = (cand.claim or "").strip()
    if len(claim) < 3:
        return None
    # Guardrail: LLM must not smuggle facts under wrong labels.
    if cand.source_type == "llm" and kind == "fact":
        kind = "hypothesis"

    claim_key = (cand.claim_key or "").strip()[:160] or None
    if claim_key:
        existing = await session.scalar(
            select(BrainEvidence).where(
                BrainEvidence.brand_id == brand_id,
                BrainEvidence.claim_key == claim_key,
                BrainEvidence.status == "active",
            )
        )
        if existing is not None:
            if existing.claim.strip() == claim[:1000]:
                # Duplicate — keep prior row; do not invent a second "fact".
                return existing
            # Contradiction / supersession: keep history, mark prior.
            new_row = BrainEvidence(
                id=uuid.uuid4(),
                organization_id=organization_id,
                brand_id=brand_id,
                research_job_id=research_job_id,
                kind=kind,
                category=category,
                claim=claim[:1000],
                confidence=max(0, min(100, int(cand.confidence))),
                status="active",
                claim_key=claim_key,
                source_url=(cand.source_url or fallback_url or "")[:500] or None,
                source_type=cand.source_type[:32],
                snippet=(cand.snippet or None),
            )
            session.add(new_row)
            await session.flush()
            existing.status = "contradicted"
            existing.superseded_by_id = new_row.id
            return new_row

    row = BrainEvidence(
        organization_id=organization_id,
        brand_id=brand_id,
        research_job_id=research_job_id,
        kind=kind,
        category=category,
        claim=claim[:1000],
        confidence=max(0, min(100, int(cand.confidence))),
        status="active",
        claim_key=claim_key,
        source_url=(cand.source_url or fallback_url or "")[:500] or None,
        source_type=cand.source_type[:32],
        snippet=(cand.snippet or None),
    )
    session.add(row)
    return row
