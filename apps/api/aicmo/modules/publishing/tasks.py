"""Background publish jobs."""

from __future__ import annotations

from typing import Any

import structlog

from aicmo.modules.publishing.service import publish_all_due_posts, publish_due_posts
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope

log = structlog.get_logger()


@tenant_job
async def publish_due_scheduled_posts(
    ctx: dict, session: Any, tenant: TenantEnvelope
) -> dict:
    brand_id = tenant.brand_uuid()
    if brand_id is None:
        return {"published": 0}
    count = await publish_due_posts(session, brand_id=brand_id)
    return {"published": count}


async def publish_due_cron(ctx: dict) -> dict:
    """System cron (P0-3): every minute, publish ALL due scheduled posts
    across every tenant. NOT a `@tenant_job` — it runs without a tenant
    envelope and opens its own session. Retry is already handled per row by
    `publish_scheduled_post` (re-queues as 'scheduled' until MAX_PUBLISH_ATTEMPTS).
    """
    from aicmo.db import rls as _rls
    from aicmo.db.session import SessionLocal

    async with SessionLocal() as session:
        # System-wide op: bypass RLS so we see every tenant's due posts.
        # No-op when DB_RLS_ENABLED is false.
        await _rls.set_bypass(session, on=True)
        published = await publish_all_due_posts(session)
    if published:
        log.info("publish.cron.ran", published=published)
    return {"published": published}
