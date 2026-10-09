"""Background jobs for advisor outcome evaluation + the learning loop.

After outcomes are measured by ``evaluate_due_outcomes``, this job also forms
evidence-backed beliefs from the newly-evaluated ones (Phase 7.2) — closing the
measured-outcome -> belief loop in a single tenant-scoped pass. Both steps are
deterministic and idempotent; the LLM writes no memory, and belief confidence /
status are derived by the existing belief service, never assigned here.

Belief formation was already implemented and worker-registered
(``belief.tasks.form_brand_beliefs`` / ``belief.formation``) but was never
triggered. Running it here, right after evaluation, makes the loop reliable and
end-to-end testable rather than depending on a job that nothing enqueues.

``enqueue_learning_cycle_cron`` is the scheduler for that job (Phase 7.5
follow-up). Mirroring ``operations_cycle_cron``, it fans out one
``evaluate_advisor_outcomes`` per active brand on a daily cron, so the learning
loop runs automatically instead of only when something manually enqueues it. It
adds NO new engine/scheduler/DB: it reuses the existing registered job, the
existing enqueue path (which respects the ``jobs_enabled`` kill switch), and
arq's own ``_job_id`` dedup to keep daily runs idempotent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from aicmo.config import get_settings
from aicmo.db.session import SessionLocal
from aicmo.modules.advisor.outcomes import evaluate_due_outcomes
from aicmo.modules.belief import formation
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope, enqueue_tenant_job
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# member_id / permissions are not needed for server-side belief writes; the job
# runs a fixed, pre-authorized unit of work under the enqueued tenant scope.
_NIL_UUID = uuid.UUID(int=0)

_LEARNING_JOB = "evaluate_advisor_outcomes"


def _context_from_envelope(env: TenantEnvelope) -> TenantContext:
    return TenantContext(
        user_id=env.user_uuid,
        user_uuid=env.user_id_uuid(),
        organization_id=env.org_uuid(),
        brand_id=env.brand_uuid(),
        member_id=_NIL_UUID,
        role_slugs=frozenset(env.role_slugs),
        permissions=frozenset(),
    )


@tenant_job
async def evaluate_advisor_outcomes(
    ctx: dict, session: Any, tenant: TenantEnvelope
) -> dict:
    """Evaluate pending outcomes, then form beliefs from the evaluated ones.

    ``form_beliefs_for_brand`` consumes only ``evaluated`` outcomes
    (insufficient_data / failed / unexecuted are skipped), is idempotent
    (already-formed outcomes are never reprocessed), and runs the deterministic
    reconciliation pass. Brand-scoped to the enqueued tenant.
    """
    count = await evaluate_due_outcomes(session, brand_id=tenant.brand_uuid())
    beliefs_formed = 0
    if tenant.brand_id is not None:
        results = await formation.form_beliefs_for_brand(
            session, tenant=_context_from_envelope(tenant)
        )
        beliefs_formed = sum(1 for r in results if r.status in ("created", "updated"))
    return {"evaluated": count, "beliefs_formed": beliefs_formed}


async def _active_brands_with_owner(session: Any) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """(brand_id, organization_id, owner_user_id) for every active brand,
    system-wide. RLS-bypassed like the publish/operations crons so the daily
    scheduler can see all tenants; each enqueued job re-scopes to its own brand."""
    from aicmo.modules.brands.models import Brand
    from aicmo.modules.orgs.models import Organization

    try:
        from aicmo.db import rls as _rls

        await _rls.set_bypass(session, on=True)
    except Exception as e:
        log.warning("learning.cron.rls_bypass_failed", error=str(e)[:120])

    stmt = (
        select(Brand.id, Brand.organization_id, Organization.owner_user_id)
        .join(Organization, Organization.id == Brand.organization_id)
        .where(Brand.status == "active")
    )
    return [(r[0], r[1], r[2]) for r in (await session.execute(stmt)).all()]


async def enqueue_learning_cycle_cron(ctx: dict) -> dict:
    """Daily scheduler for the learning loop. Fans out one
    ``evaluate_advisor_outcomes`` per active brand (evaluate due outcomes -> form
    eligible beliefs -> reconcile). Never raises — a scheduler that throws would
    take the whole worker cron loop down.

    Safety/idempotency, reusing existing mechanisms only:
      * respects the ``jobs_enabled`` kill switch (via enqueue_tenant_job, and
        checked up front so a disabled platform enqueues nothing);
      * each job's authorized scope is server-derived from the DB (the brand's
        org + owner), never from input — tenant isolation preserved;
      * a deterministic daily ``_job_id`` per brand lets arq dedup overlapping or
        repeated fires (no global lock);
      * the downstream job is itself idempotent, so a re-run forms no new beliefs.
    """
    settings = get_settings()
    if not settings.jobs_enabled:
        return {"status": "disabled", "note": "Background jobs are switched off."}
    pool = ctx.get("redis")
    if pool is None:
        log.warning("learning.cron.no_pool")
        return {"status": "no_pool", "enqueued": 0}

    try:
        async with SessionLocal() as session:
            brands = await _active_brands_with_owner(session)
    except Exception as e:
        log.warning("learning.cron.scan_failed", error=str(e)[:200])
        return {"status": "failed", "enqueued": 0}

    bucket = datetime.now(UTC).strftime("%Y-%m-%d")  # one run per brand per day
    enqueued = 0
    for brand_id, org_id, owner_user_id in brands:
        tenant = TenantContext(
            user_id=str(owner_user_id),
            user_uuid=owner_user_id,
            organization_id=org_id,
            brand_id=brand_id,
            member_id=_NIL_UUID,
            role_slugs=frozenset(),
            permissions=frozenset(),
        )
        try:
            job = await enqueue_tenant_job(
                pool, _LEARNING_JOB, tenant=tenant, _job_id=f"learning:{brand_id}:{bucket}"
            )
        except Exception as e:
            log.warning("learning.cron.enqueue_failed", brand_id=str(brand_id), error=str(e)[:120])
            continue
        if job is not None:
            enqueued += 1

    log.info("learning.cron.enqueued", brands=len(brands), enqueued=enqueued)
    return {"status": "ok", "brands": len(brands), "enqueued": enqueued}
