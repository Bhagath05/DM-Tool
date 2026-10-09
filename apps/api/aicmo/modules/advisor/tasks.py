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
"""

from __future__ import annotations

import uuid
from typing import Any

from aicmo.modules.advisor.outcomes import evaluate_due_outcomes
from aicmo.modules.belief import formation
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope
from aicmo.tenancy.context import TenantContext

# member_id / permissions are not needed for server-side belief writes; the job
# runs a fixed, pre-authorized unit of work under the enqueued tenant scope.
_NIL_UUID = uuid.UUID(int=0)


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
