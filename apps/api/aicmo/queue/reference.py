"""Reference job — Phase 0.

A trivial tenant-scoped job used only to prove the harness works
end-to-end (see tests/queue/). It counts rows in `leads` under the
restored tenant context — so under RLS-on it must see only the
enqueuing tenant's rows. No product behavior depends on it.

This file is also the template every real `modules/<name>/tasks.py`
job should follow: decorate with @tenant_job, take
`(ctx, session, tenant, ...)`, and use `session` for all DB work.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from aicmo.modules.leads.models import Lead
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope


@tenant_job
async def echo_tenant_job(ctx: dict, session: Any, tenant: TenantEnvelope) -> dict:
    """Return the restored tenant + a tenant-scoped count. Test-only."""
    stmt = select(func.count()).select_from(Lead).where(
        Lead.organization_id == tenant.org_uuid()
    )
    lead_count = (await session.execute(stmt)).scalar_one()
    return {
        "organization_id": tenant.organization_id,
        "brand_id": tenant.brand_id,
        "lead_count": int(lead_count),
    }
