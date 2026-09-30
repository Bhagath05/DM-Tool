"""Belief memory write/derivation service (server-side only).

There is NO LLM-facing write path: beliefs are created/updated exclusively by
server code holding a trusted TenantContext. Brand/org scope always comes from
that context — never from input. Evidence references are validated to belong to
the same tenant (cross-tenant references are rejected), statements are scanned
for secrets, and confidence is DERIVED from evidence, never taken from a caller.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief.confidence import derive_confidence, derive_status
from aicmo.modules.belief.enums import (
    DB_BACKED_REFS,
    EXPERIMENTAL_REF_KINDS,
    BeliefStatus,
    EvidenceRefKind,
    EvidenceRelation,
)
from aicmo.modules.belief.models import Belief, BeliefEvidence
from aicmo.modules.belief.schemas import BeliefCreate, EvidenceRefInput
from aicmo.tenancy.context import TenantContext

_MAX_SCOPE_KEYS = 12
_MAX_SCOPE_VALUE = 400
_TERMINAL = {BeliefStatus.SUPERSEDED.value, BeliefStatus.RETIRED.value}

# High-signal secret shapes only (avoids false positives on ordinary marketing
# prose that merely mentions the word "password").
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|AKIA[0-9A-Z]{12,}|xox[bap]-[a-z0-9-]{10,}|-----BEGIN|"
    r"(api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret|smtp[_-]?password)\s*[:=]\s*\S+|"
    r"bearer\s+[a-z0-9._-]{20,})"
)


class BeliefNotFoundError(LookupError):
    """No such belief for this tenant (also the cross-tenant miss)."""


class BeliefValidationError(ValueError):
    """A belief write violated a domain rule (bad evidence, secret, etc.)."""


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise BeliefValidationError("A brand must be selected to work with beliefs.")
    return tenant.brand_id


def _assert_safe_text(*values: str | None) -> None:
    for v in values:
        if v and _SECRET_RE.search(v):
            raise BeliefValidationError("Refusing to store a belief that contains a secret-like value.")


def _bounded_scope(scope: dict) -> dict:
    if not isinstance(scope, dict):
        raise BeliefValidationError("scope must be an object.")
    out: dict = {}
    for k, v in list(scope.items())[:_MAX_SCOPE_KEYS]:
        text_val = v if isinstance(v, str) else str(v)
        _assert_safe_text(str(k), text_val)
        out[str(k)[:64]] = text_val[:_MAX_SCOPE_VALUE]
    return out


async def _validate_ref_ownership(
    session: AsyncSession, tenant: TenantContext, ref: EvidenceRefInput
) -> None:
    if ref.ref_kind == EvidenceRefKind.DATA_SOURCE:
        if not (ref.note and ref.note.strip()):
            raise BeliefValidationError("data_source evidence requires a provenance note.")
        _assert_safe_text(ref.note)
        return
    if ref.ref_id is None:
        raise BeliefValidationError(f"{ref.ref_kind.value} evidence requires a ref_id.")
    _assert_safe_text(ref.note)
    table = DB_BACKED_REFS[ref.ref_kind.value]  # hardcoded allowlist — safe
    row = (
        await session.execute(
            text(f"SELECT 1 FROM {table} WHERE id = :id AND brand_id = :brand"),
            {"id": ref.ref_id, "brand": tenant.brand_id},
        )
    ).first()
    if row is None:
        # Nonexistent OR another tenant's row → rejected. Never leak which.
        raise BeliefValidationError(
            f"evidence {ref.ref_kind.value}:{ref.ref_id} is not available for this brand."
        )


async def _load_refs(session: AsyncSession, belief_id: uuid.UUID) -> list[BeliefEvidence]:
    return list(
        (
            await session.execute(
                select(BeliefEvidence)
                .where(BeliefEvidence.belief_id == belief_id)
                .order_by(BeliefEvidence.created_at.asc(), BeliefEvidence.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def _recompute(session: AsyncSession, belief: Belief) -> None:
    """Re-derive confidence + status from the belief's evidence. No-op for a
    terminal (superseded/retired) belief — its history is frozen."""
    if belief.status in _TERMINAL:
        return
    refs = await _load_refs(session, belief.id)
    supports = sum(1 for r in refs if r.relation == EvidenceRelation.SUPPORTS.value)
    contradicts = sum(1 for r in refs if r.relation == EvidenceRelation.CONTRADICTS.value)
    experimental = any(
        r.relation == EvidenceRelation.SUPPORTS.value and r.ref_kind in EXPERIMENTAL_REF_KINDS
        for r in refs
    )
    confidence, reason = derive_confidence(
        supports=supports, contradicts=contradicts, experimental=experimental
    )
    status = derive_status(supports=supports, contradicts=contradicts)
    belief.confidence = confidence
    belief.confidence_reason = reason
    belief.evidence_count = len(refs)
    belief.status = status.value
    belief.validated_at = datetime.now(UTC) if supports > 0 else None
    await session.flush()


async def create_belief(session: AsyncSession, *, tenant: TenantContext, data: BeliefCreate) -> Belief:
    brand_id = _require_brand(tenant)
    _assert_safe_text(data.statement, data.subject_key)
    scope = _bounded_scope(data.scope)
    for ref in data.evidence:
        await _validate_ref_ownership(session, tenant, ref)

    belief = Belief(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        category=data.category.value,
        subject_key=data.subject_key,
        statement=data.statement,
        scope=scope,
        status=BeliefStatus.UNVALIDATED.value,
    )
    session.add(belief)
    await session.flush()
    for ref in data.evidence:
        session.add(
            BeliefEvidence(
                organization_id=tenant.organization_id,
                brand_id=brand_id,
                belief_id=belief.id,
                ref_kind=ref.ref_kind.value,
                ref_id=ref.ref_id,
                relation=ref.relation.value,
                note=ref.note,
            )
        )
    await session.flush()
    await _recompute(session, belief)
    return belief


async def get_belief(session: AsyncSession, *, tenant: TenantContext, belief_id: uuid.UUID) -> Belief:
    brand_id = _require_brand(tenant)
    belief = (
        await session.execute(
            select(Belief).where(
                Belief.id == belief_id,
                Belief.brand_id == brand_id,
                Belief.organization_id == tenant.organization_id,
            )
        )
    ).scalar_one_or_none()
    if belief is None:
        raise BeliefNotFoundError(str(belief_id))
    return belief


async def add_evidence(
    session: AsyncSession, *, tenant: TenantContext, belief_id: uuid.UUID, ref: EvidenceRefInput
) -> Belief:
    belief = await get_belief(session, tenant=tenant, belief_id=belief_id)
    await _validate_ref_ownership(session, tenant, ref)
    session.add(
        BeliefEvidence(
            organization_id=tenant.organization_id,
            brand_id=belief.brand_id,
            belief_id=belief.id,
            ref_kind=ref.ref_kind.value,
            ref_id=ref.ref_id,
            relation=ref.relation.value,
            note=ref.note,
        )
    )
    await session.flush()
    await _recompute(session, belief)
    return belief


async def supersede_belief(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    old_belief_id: uuid.UUID,
    new_belief_id: uuid.UUID,
) -> None:
    """Mark ``old`` superseded by ``new`` (both must belong to this tenant, so
    supersession can never cross tenants). History is retained, not deleted."""
    old = await get_belief(session, tenant=tenant, belief_id=old_belief_id)
    new = await get_belief(session, tenant=tenant, belief_id=new_belief_id)
    old.status = BeliefStatus.SUPERSEDED.value
    old.superseded_by_id = new.id
    old.valid_until = datetime.now(UTC)
    new.parent_belief_id = old.id
    await session.flush()


async def update_from_outcome(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    belief_id: uuid.UUID,
    outcome_id: uuid.UUID,
    relation: EvidenceRelation,
) -> Belief:
    """Record a measured advisor outcome as evidence for/against a belief and
    re-derive confidence. A contradicting outcome lowers confidence and can flip
    the belief to CONTRADICTED — never asserting causality, only recording it."""
    ref = EvidenceRefInput(
        ref_kind=EvidenceRefKind.ADVISOR_OUTCOME, ref_id=outcome_id, relation=relation
    )
    return await add_evidence(session, tenant=tenant, belief_id=belief_id, ref=ref)
