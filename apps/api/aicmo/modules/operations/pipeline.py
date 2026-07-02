"""Phase 4.6 — Trigger → Decision → Action pipeline.

Completes the continuous lifecycle by wiring the REASONING engines into the loop:
  observe (4.1) → detect (4.2) → DECIDE (reuse Decision Engine) → act (policy-
  gated work) ... and periodically LEARN (reuse Learning synthesis). No new
  reasoning is written here — it reuses decision_engine.decide and
  learning.synthesis.synthesize, and the Autonomy Policy still gates every action.

Cost-controlled + safe: the whole reasoning layer is OFF unless
`operations_pipeline_enabled`; each engine runs at most once per brand per
cooldown; decisions become policy-gated work (nothing executes). Event-triggered:
the Decision Engine only runs when high-severity events are actually open.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.operations import scheduler
from aicmo.modules.operations.models import DetectedEvent, ScheduledWork

log = structlog.get_logger()

# urgency → work priority.
_URGENCY_PRIORITY = {"now": "high", "this_week": "high", "this_month": "medium", "monitor": "low"}


def _system_tenant(org_id: uuid.UUID, brand_id: uuid.UUID):
    """A minimal tenant context for system-driven engine runs. The reused engines
    read only brand_id/organization_id/user_id."""
    return SimpleNamespace(
        user_id="system",
        organization_id=org_id,
        brand_id=brand_id,
    )


def _action_type_for(channels: list[str]) -> tuple[str, str]:
    """(kind, autonomy action_type) for a decision, from its channels."""
    ch = " ".join(channels).lower()
    if "email" in ch:
        return "email", "email_sending"
    if "ad" in ch:
        return "ad", "ad_creation"
    return "campaign_update", "campaign_creation"


async def _last_created(
    session: AsyncSession, model, brand_id: uuid.UUID, **filters
) -> datetime | None:
    stmt = select(model.created_at).where(model.brand_id == brand_id)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    stmt = stmt.order_by(desc(model.created_at)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _cooldown_elapsed(
    session: AsyncSession, model, *, brand_id: uuid.UUID, seconds: int, now: datetime, **filters
) -> bool:
    last = await _last_created(session, model, brand_id, **filters)
    return last is None or last < now - timedelta(seconds=seconds)


async def _open_high_sev_events(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> list[DetectedEvent]:
    stmt = select(DetectedEvent).where(
        DetectedEvent.brand_id == brand_id,
        DetectedEvent.status == "new",
        DetectedEvent.severity.in_(("critical", "high")),
    )
    return list((await session.execute(stmt)).scalars().all())


async def run_reasoning(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    now: datetime | None = None,
) -> dict:
    """Run the gated reasoning steps for one brand. Returns a small counts dict.
    Never raises meaningfully — callers guard, but each engine is also try-safe."""
    now = now or datetime.now(UTC)
    settings = get_settings()
    result = {"enabled": False, "decisions": 0, "work_from_decisions": 0, "learning_ran": False}

    if not settings.operations_pipeline_enabled:
        return result
    result["enabled"] = True
    tenant = _system_tenant(organization_id, brand_id)

    # --- DECIDE: event-triggered, cooldown-limited ------------------------
    open_events = await _open_high_sev_events(session, brand_id=brand_id)
    if open_events and await _cooldown_elapsed(
        session, ScheduledWork, brand_id=brand_id,
        seconds=settings.operations_decision_cooldown_seconds, now=now,
        source_kind="decision",
    ):
        try:
            from aicmo.modules.decision_engine.service import decide

            report = (await decide(session, tenant=tenant)).report
            drafts = []
            for d in report.decisions:
                kind, action_type = _action_type_for(d.affected_channels)
                digest = hashlib.sha1(
                    d.decision.lower().encode("utf-8")
                ).hexdigest()[:12]
                drafts.append(scheduler.WorkDraft(
                    kind=kind, action_type=action_type,
                    title=d.decision, description=d.recommended_action,
                    rationale=f"{d.reasoning} (serves: {d.business_objective})",
                    priority=_URGENCY_PRIORITY.get(d.urgency, "medium"),
                    source_kind="decision", dedupe_hint=digest,
                ))
            result["decisions"] = len(drafts)
            result["work_from_decisions"] = await scheduler.persist_drafts(
                session, organization_id=organization_id, brand_id=brand_id, drafts=drafts
            )
            # Mark the triggering events acknowledged (they've been reasoned on).
            for ev in open_events:
                ev.status = "acknowledged"
            await session.commit()  # persist the decision work + event acks
        except Exception as e:
            await session.rollback()
            log.warning("ops.pipeline.decide_failed", brand_id=str(brand_id), error=str(e)[:160])

    # --- LEARN: periodic, cooldown-limited --------------------------------
    from aicmo.modules.learning.models import LearningInsight

    if await _cooldown_elapsed(
        session, LearningInsight, brand_id=brand_id,
        seconds=settings.operations_learning_cooldown_seconds, now=now,
    ):
        try:
            from aicmo.modules.learning.synthesis import synthesize

            await synthesize(session, tenant=tenant)
            result["learning_ran"] = True
        except Exception as e:
            log.warning("ops.pipeline.learn_failed", brand_id=str(brand_id), error=str(e)[:160])

    return result
