"""Background jobs for advisor outcome evaluation."""

from __future__ import annotations

from typing import Any

from aicmo.modules.advisor.outcomes import evaluate_due_outcomes
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope


@tenant_job
async def evaluate_advisor_outcomes(
    ctx: dict, session: Any, tenant: TenantEnvelope
) -> dict:
    """Evaluate pending outcomes for the enqueued tenant."""
    count = await evaluate_due_outcomes(session, brand_id=tenant.brand_uuid())
    return {"evaluated": count}
