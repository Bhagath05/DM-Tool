"""Automated belief formation from evaluated outcomes (Phase 3C).

A server-side evidence-to-memory pipeline:

    evaluated advisor outcome  ->  deterministic belief candidate
                               ->  existing Phase-3A belief service
                               ->  create / add-evidence (idempotent)

No LLM writes memory. Belief statements are fully server-templated from
CONTROLLED fields (action kind + measurement window) — no free-text outcome
content is interpolated, so outcome text can never become instructions, and no
causal claim is asserted (only a measured association). Confidence/status are
derived by the existing deterministic system; the pipeline never sets them.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
from aicmo.modules.belief import service as belief_service
from aicmo.modules.belief.enums import BeliefCategory, EvidenceRefKind, EvidenceRelation
from aicmo.modules.belief.models import Belief, BeliefEvidence
from aicmo.modules.belief.schemas import BeliefCreate, EvidenceRefInput
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

_ELIGIBLE_STATUS = "evaluated"  # the canonical "measured" state from _evaluate_one
_TERMINAL = {"superseded", "retired"}
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_TOKEN_RE = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class BeliefCandidate:
    category: BeliefCategory
    subject_key: str
    statement: str
    scope: dict
    relation: EvidenceRelation


@dataclass(frozen=True)
class FormationResult:
    status: str  # created | updated | skipped | not_eligible | rejected
    outcome_id: uuid.UUID
    belief_id: uuid.UUID | None = None
    reason: str | None = None


def _safe_token(value: str | None, *, fallback: str) -> str:
    """Normalize an internal field to a bounded [a-z0-9_] token — defense in
    depth so nothing free-form (even if a field were tampered) shapes identity."""
    token = _TOKEN_RE.sub("_", (value or "").strip().lower()).strip("_")
    return (token or fallback)[:48]


def derive_candidate(outcome: AdvisorOutcome, recommendation: AdvisorRecommendation | None) -> BeliefCandidate | None:
    """Deterministically map an EVALUATED outcome to a belief candidate, or None
    if the outcome is not eligible (insufficient/pending). Pure — no DB, no LLM."""
    if outcome.evaluation_status != _ELIGIBLE_STATUS:
        return None  # insufficient_data / pending → not a strong belief
    if outcome.effectiveness_score is None:
        return None
    surface = _safe_token(getattr(recommendation, "source_surface", None), fallback="advisor")
    record_type = _safe_token(getattr(recommendation, "record_type", None), fallback="action")
    # Improved/neutral → supports the association; declined → contradicts it.
    relation = (
        EvidenceRelation.SUPPORTS if outcome.effectiveness_score >= 50 else EvidenceRelation.CONTRADICTS
    )
    subject_key = f"outcome_effect:{surface}:{record_type}"[:200]
    statement = (
        f"Across measured 14-day windows, acting on '{surface}' recommendations showed a "
        f"measurable association with lead volume for this brand. This is a correlation from "
        f"measured outcomes, not a causal claim."
    )
    scope = {
        "window": "14_day",
        "action_kind": surface,
        "record_type": record_type,
        "measured_via": "advisor_outcome",
    }
    return BeliefCandidate(
        category=BeliefCategory.PERFORMANCE,
        subject_key=subject_key,
        statement=statement,
        scope=scope,
        relation=relation,
    )


async def _already_formed(session: AsyncSession, *, brand_id: uuid.UUID, outcome_id: uuid.UUID) -> bool:
    """True if this outcome is already referenced by a belief for this brand."""
    row = (
        await session.execute(
            select(BeliefEvidence.id).where(
                BeliefEvidence.brand_id == brand_id,
                BeliefEvidence.ref_kind == EvidenceRefKind.ADVISOR_OUTCOME.value,
                BeliefEvidence.ref_id == outcome_id,
            )
        )
    ).first()
    return row is not None


async def _existing_belief(
    session: AsyncSession, *, brand_id: uuid.UUID, organization_id: uuid.UUID, subject_key: str
) -> Belief | None:
    return (
        await session.execute(
            select(Belief)
            .where(
                Belief.brand_id == brand_id,
                Belief.organization_id == organization_id,
                Belief.subject_key == subject_key,
                Belief.status.notin_(_TERMINAL),
            )
            .order_by(Belief.created_at.asc(), Belief.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def form_belief_from_outcome(
    session: AsyncSession, *, tenant: TenantContext, outcome_id: uuid.UUID
) -> FormationResult:
    """Form/refresh a belief from one evaluated outcome. Idempotent, tenant-safe.

    The outcome is loaded scoped to the tenant brand (cross-tenant → rejected).
    Confidence/status are derived by the belief service, not here."""
    brand_id = belief_service._require_brand(tenant)
    outcome = (
        await session.execute(
            select(AdvisorOutcome).where(
                AdvisorOutcome.id == outcome_id, AdvisorOutcome.brand_id == brand_id
            )
        )
    ).scalar_one_or_none()
    if outcome is None:
        # Nonexistent OR another tenant's outcome → fail closed, never leak.
        return FormationResult(status="rejected", outcome_id=outcome_id, reason="outcome_not_for_tenant")

    recommendation = (
        await session.execute(
            select(AdvisorRecommendation).where(
                AdvisorRecommendation.id == outcome.recommendation_id,
                AdvisorRecommendation.brand_id == brand_id,
            )
        )
    ).scalar_one_or_none()

    candidate = derive_candidate(outcome, recommendation)
    if candidate is None:
        return FormationResult(status="not_eligible", outcome_id=outcome_id, reason="outcome_not_evaluated")

    if await _already_formed(session, brand_id=brand_id, outcome_id=outcome_id):
        return FormationResult(status="skipped", outcome_id=outcome_id, reason="already_formed")

    ref = EvidenceRefInput(
        ref_kind=EvidenceRefKind.ADVISOR_OUTCOME, ref_id=outcome_id, relation=candidate.relation
    )
    existing = await _existing_belief(
        session, brand_id=brand_id, organization_id=tenant.organization_id, subject_key=candidate.subject_key
    )
    if existing is not None:
        belief = await belief_service.add_evidence(
            session, tenant=tenant, belief_id=existing.id, ref=ref
        )
        result = FormationResult(status="updated", outcome_id=outcome_id, belief_id=belief.id)
    else:
        belief = await belief_service.create_belief(
            session,
            tenant=tenant,
            data=BeliefCreate(
                category=candidate.category,
                subject_key=candidate.subject_key,
                statement=candidate.statement,
                scope=candidate.scope,
                evidence=[ref],
            ),
        )
        result = FormationResult(status="created", outcome_id=outcome_id, belief_id=belief.id)

    # Provenance is inherent (belief_evidence → outcome); log a safe event too.
    log.info(
        "belief.formed",
        status=result.status,
        belief_id=str(result.belief_id),
        outcome_id=str(outcome_id),
        organization_id=str(tenant.organization_id),
        brand_id=str(brand_id),
    )
    return result


async def form_beliefs_for_brand(
    session: AsyncSession, *, tenant: TenantContext, limit: int = _DEFAULT_LIMIT
) -> list[FormationResult]:
    """Form beliefs for the brand's evaluated-but-not-yet-formed outcomes.
    Bounded + deterministic ordering; safe to re-run (idempotent)."""
    brand_id = belief_service._require_brand(tenant)
    limit = max(1, min(limit, _MAX_LIMIT))
    already = select(BeliefEvidence.ref_id).where(
        BeliefEvidence.brand_id == brand_id,
        BeliefEvidence.ref_kind == EvidenceRefKind.ADVISOR_OUTCOME.value,
        BeliefEvidence.ref_id.is_not(None),
    )
    outcomes = (
        (
            await session.execute(
                select(AdvisorOutcome)
                .where(
                    and_(
                        AdvisorOutcome.brand_id == brand_id,
                        AdvisorOutcome.evaluation_status == _ELIGIBLE_STATUS,
                        AdvisorOutcome.id.notin_(already),
                    )
                )
                .order_by(AdvisorOutcome.evaluated_at.asc(), AdvisorOutcome.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    results: list[FormationResult] = []
    for outcome in outcomes:
        results.append(await form_belief_from_outcome(session, tenant=tenant, outcome_id=outcome.id))
    return results
