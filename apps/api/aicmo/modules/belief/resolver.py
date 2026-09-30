"""Deterministic belief retrieval for the (future) agent.

Returns a BOUNDED, ordered snapshot — active beliefs with their evidence
references, and optionally the superseded/contradicted history — so the agent
never has to load every historical belief into a prompt. Strictly tenant/brand
scoped; ordering is deterministic for reproducibility.
"""

from __future__ import annotations

import uuid

from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief.enums import BeliefStatus
from aicmo.modules.belief.models import Belief, BeliefEvidence
from aicmo.modules.belief.schemas import (
    BeliefResolution,
    BeliefView,
    EvidenceRefView,
)
from aicmo.tenancy.context import TenantContext

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 100
_CONTEXT_MAX_BELIEFS = 12


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise ValueError("A brand must be selected to resolve beliefs.")
    return tenant.brand_id


async def _views(session: AsyncSession, beliefs: list[Belief]) -> list[BeliefView]:
    if not beliefs:
        return []
    ids = [b.id for b in beliefs]
    refs = (
        (
            await session.execute(
                select(BeliefEvidence)
                .where(BeliefEvidence.belief_id.in_(ids))
                .order_by(asc(BeliefEvidence.created_at), asc(BeliefEvidence.id))
            )
        )
        .scalars()
        .all()
    )
    by_belief: dict[uuid.UUID, list[EvidenceRefView]] = {}
    for r in refs:
        # model_validate coerces the String columns into their StrEnum types.
        by_belief.setdefault(r.belief_id, []).append(
            EvidenceRefView.model_validate(
                {"ref_kind": r.ref_kind, "ref_id": r.ref_id, "relation": r.relation, "note": r.note}
            )
        )
    return [
        BeliefView.model_validate(
            {
                "id": b.id,
                "category": b.category,
                "subject_key": b.subject_key,
                "statement": b.statement,
                "scope": b.scope,
                "status": b.status,
                "confidence": b.confidence,
                "confidence_reason": b.confidence_reason,
                "evidence_count": b.evidence_count,
                "validated_at": b.validated_at,
                "valid_from": b.valid_from,
                "valid_until": b.valid_until,
                "superseded_by_id": b.superseded_by_id,
                "parent_belief_id": b.parent_belief_id,
                "created_at": b.created_at,
                "updated_at": b.updated_at,
                "evidence": by_belief.get(b.id, []),
            }
        )
        for b in beliefs
    ]


async def _query(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    organization_id: uuid.UUID,
    status: str,
    category: str | None,
    subject_key: str | None,
    limit: int,
) -> list[Belief]:
    stmt = select(Belief).where(
        Belief.brand_id == brand_id,
        Belief.organization_id == organization_id,
        Belief.status == status,
    )
    if category is not None:
        stmt = stmt.where(Belief.category == category)
    if subject_key is not None:
        stmt = stmt.where(Belief.subject_key == subject_key)
    # Deterministic ordering: category, subject, confidence desc, id.
    stmt = stmt.order_by(
        asc(Belief.category), asc(Belief.subject_key), desc(Belief.confidence), asc(Belief.id)
    ).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def resolve_beliefs(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    category: str | None = None,
    subject_key: str | None = None,
    include_history: bool = False,
    limit: int = _DEFAULT_LIMIT,
) -> BeliefResolution:
    brand_id = _require_brand(tenant)
    org_id = tenant.organization_id
    limit = max(1, min(limit, _MAX_LIMIT))

    active_rows = await _query(
        session, brand_id=brand_id, organization_id=org_id, status=BeliefStatus.ACTIVE.value,
        category=category, subject_key=subject_key, limit=limit + 1,
    )
    truncated = len(active_rows) > limit
    active_rows = active_rows[:limit]

    superseded_views: list[BeliefView] = []
    contradicted_views: list[BeliefView] = []
    if include_history:
        superseded_rows = await _query(
            session, brand_id=brand_id, organization_id=org_id, status=BeliefStatus.SUPERSEDED.value,
            category=category, subject_key=subject_key, limit=limit,
        )
        contradicted_rows = await _query(
            session, brand_id=brand_id, organization_id=org_id, status=BeliefStatus.CONTRADICTED.value,
            category=category, subject_key=subject_key, limit=limit,
        )
        superseded_views = await _views(session, superseded_rows)
        contradicted_views = await _views(session, contradicted_rows)

    return BeliefResolution(
        brand_id=brand_id,
        active=await _views(session, active_rows),
        superseded=superseded_views,
        contradicted=contradicted_views,
        truncated=truncated,
    )


def to_context_block(resolution: BeliefResolution, *, max_beliefs: int = _CONTEXT_MAX_BELIEFS) -> str:
    """A bounded, deterministic prompt fragment. Only ACTIVE beliefs, each with
    its confidence + reason so the agent never treats a guess as fact."""
    lines = ["=== ACTIVE BELIEFS (evidence-derived; not certainties) ==="]
    if not resolution.active:
        lines.append("- (none held yet — treat as INSUFFICIENT_EVIDENCE)")
        return "\n".join(lines)
    for b in resolution.active[:max_beliefs]:
        scope = ", ".join(f"{k}={v}" for k, v in list(b.scope.items())[:4]) or "unscoped"
        lines.append(
            f"- [{b.category}] {b.statement[:240]} "
            f"(confidence {b.confidence}%, {b.evidence_count} evidence; scope: {scope})"
        )
    if resolution.truncated:
        lines.append("- …(more active beliefs not shown)")
    return "\n".join(lines)
