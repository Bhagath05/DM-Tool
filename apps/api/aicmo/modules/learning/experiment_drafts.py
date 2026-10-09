"""Phase 7.4 — persist a BRO experiment proposal as a reversible internal draft.

A *draft* is the least-consequential artifact in the system: every autonomy
level, down to fully-manual, permits the AI to draft and advise. So this service
always creates the draft — it never spends, publishes, or sends — and reuses the
EXISTING ``AdvisorRecommendation`` as the store (``record_type="experiment"`` with
the validated proposal in ``generator_hint``). No new table, no migration.

What the autonomy policy governs is the *downstream* consequential step (acting
on the draft — launching/publishing/spending). We record that policy decision on
the draft (via ``autonomy_service.evaluate_policy("ai_decision", master_switch)``)
so the UI and any later executor know whether acting on it may be automated or
must wait for a human — but the draft itself is created regardless and is fully
reversible.

Guarantees:
  * validated — the proposal passes the server-side experiment contract first;
  * tenant-scoped — org/brand come only from the TenantContext, never input;
  * idempotent — a deterministic id from (brand, proposal fingerprint) means a
    retry or a re-proposal of the same experiment updates in place, never dupes;
  * auditable — an ``experiment.draft_created`` audit row is written;
  * never self-granting — this is a plain server service; the conversational LLM
    runtime (READ + propose-consequential only) does not call it.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.advisor.dedupe import recommendation_id_from_fingerprint
from aicmo.modules.advisor.models import AdvisorRecommendation
from aicmo.modules.audit import service as audit_service
from aicmo.modules.autonomy import service as autonomy_service
from aicmo.modules.learning.experiment_contract import (
    ExperimentProposal,
    proposal_fingerprint,
    validate_proposal,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

_RECORD_TYPE = "experiment"
_SOURCE_SURFACE = "bro_experiment"
# Acting on a marketing experiment (launch/publish/spend) is a strategic AI
# decision — that is the autonomy action the downstream step is gated by.
_AUTONOMY_ACTION = "ai_decision"


class ExperimentDraftResult(BaseModel):
    """Outcome of creating/refreshing a draft. ``requires_approval`` reflects the
    autonomy policy for ACTING on the draft — not for creating it (creation is
    always allowed and reversible)."""

    recommendation_id: uuid.UUID
    created: bool
    fingerprint: str
    status: str
    autonomy_mode: str
    requires_approval: bool
    autonomy_reason: str


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise ValueError("A brand must be selected to draft an experiment.")
    return tenant.brand_id


async def create_experiment_draft(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    proposal: ExperimentProposal | dict,
) -> ExperimentDraftResult:
    """Validate a proposal and persist it as a reversible draft. Idempotent per
    (brand, proposal fingerprint). Does not commit — the caller owns the txn."""
    brand_id = _require_brand(tenant)
    proposal = validate_proposal(proposal)
    fingerprint = proposal_fingerprint(proposal)
    # Brand-scoped deterministic id: same proposal in the same brand → same row.
    rec_id = recommendation_id_from_fingerprint(f"experiment|{brand_id}|{fingerprint}")

    # The autonomy decision for ACTING on the experiment later (never for the
    # draft itself). Master switch is the platform-wide execution gate (default
    # OFF) — so by default this returns requires_approval=True.
    config = await autonomy_service.get_or_default(session, brand_id=brand_id)
    decision = autonomy_service.evaluate_policy(
        config,
        _AUTONOMY_ACTION,
        execution_enabled=get_settings().autonomy_execution_enabled,
    )

    hint: dict[str, Any] = {
        "kind": "experiment_proposal",
        "proposal": proposal.model_dump(mode="json"),
        "fingerprint": fingerprint,
        "autonomy": {
            "action_type": _AUTONOMY_ACTION,
            "mode": decision.mode,
            "requires_approval": decision.requires_approval,
            "reason": decision.reason,
        },
    }
    title = f"Experiment: {proposal.hypothesis}"[:280]
    description = (
        f"Objective: {proposal.business_objective}\n"
        f"Comparison: {proposal.comparison}\n"
        f"Primary metric: {proposal.primary_metric.value} over "
        f"{proposal.measurement_window_days} days.\n"
        f"Success: {proposal.success_condition}\n"
        f"Inconclusive: {proposal.inconclusive_condition}"
    )

    existing = (
        await session.execute(
            select(AdvisorRecommendation).where(
                AdvisorRecommendation.id == rec_id,
                AdvisorRecommendation.brand_id == brand_id,
            )
        )
    ).scalar_one_or_none()

    created = existing is None
    if existing is not None:
        existing.title = title
        existing.description = description
        existing.why = proposal.hypothesis[:2000]
        existing.expected_result = proposal.success_condition[:2000]
        existing.generator_hint = hint
        existing.source_fingerprint = fingerprint
        row = existing
    else:
        row = AdvisorRecommendation(
            id=rec_id,
            organization_id=tenant.organization_id,
            brand_id=brand_id,
            user_id=tenant.user_id,
            record_type=_RECORD_TYPE,
            title=title,
            description=description,
            status="not_started",
            impact_score=0,
            confidence=0,  # a draft asserts no confidence — evidence comes later
            impact_category=None,
            why=proposal.hypothesis[:2000],
            expected_result=proposal.success_condition[:2000],
            data_used=[],
            source_surface=_SOURCE_SURFACE,
            source_fingerprint=fingerprint,
            generator_hint=hint,
        )
        session.add(row)
    await session.flush()

    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        actor_user_id=tenant.user_uuid,
        action="experiment.draft_created" if created else "experiment.draft_updated",
        target_type="advisor_recommendation",
        target_id=rec_id,
        after={"fingerprint": fingerprint, "autonomy_mode": decision.mode,
               "requires_approval": decision.requires_approval},
        metadata={"source": _SOURCE_SURFACE},
    )

    log.info(
        "experiment.draft",
        created=created,
        recommendation_id=str(rec_id),
        organization_id=str(tenant.organization_id),
        brand_id=str(brand_id),
        requires_approval=decision.requires_approval,
    )
    return ExperimentDraftResult(
        recommendation_id=rec_id,
        created=created,
        fingerprint=fingerprint,
        status=row.status,
        autonomy_mode=decision.mode,
        requires_approval=decision.requires_approval,
        autonomy_reason=decision.reason,
    )
