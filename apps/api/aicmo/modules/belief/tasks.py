"""Background job: form beliefs from evaluated outcomes for one tenant.

A companion to `evaluate_advisor_outcomes` — after outcomes are measured, this
turns eligible ones into evidence-backed beliefs through the Phase-3A service.
Retry-safe and idempotent (already-formed outcomes are skipped), bounded, and
tenant-scoped. It performs no consequential action and no LLM write.
"""

from __future__ import annotations

import uuid
from typing import Any

from aicmo.modules.belief import formation
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope
from aicmo.tenancy.context import TenantContext

# member_id / permissions are not needed for server-side belief writes; a job
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
async def form_brand_beliefs(ctx: dict, session: Any, tenant: TenantEnvelope) -> dict:
    """Form beliefs for the enqueued tenant's evaluated outcomes."""
    if tenant.brand_id is None:
        return {"formed": 0, "reason": "no_brand"}
    results = await formation.form_beliefs_for_brand(session, tenant=_context_from_envelope(tenant))
    formed = sum(1 for r in results if r.status in ("created", "updated"))
    return {"formed": formed, "processed": len(results)}
