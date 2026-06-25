"""@tenant_job — restores tenant context inside a worker job.

A request handler resolves tenant via `require_tenant`, which binds
structlog contextvars + Sentry tags + (when enabled) the RLS session
GUCs. A background job has no request, so none of that happens
automatically. This decorator re-establishes the exact same context
from the `_TenantEnvelope` that `enqueue_tenant_job` serialized.

A decorated job is called as:

    @tenant_job
    async def my_job(ctx, session, tenant, *args, **kwargs):
        # `session` is a fresh AsyncSession already scoped to the tenant
        # (RLS GUCs set when DB_RLS_ENABLED); `tenant` is the envelope.
        ...

The decorator:
  1. Pops the envelope from kwargs (raises if missing — every job MUST
     be enqueued via enqueue_tenant_job).
  2. Opens a dedicated AsyncSession (jobs never share a request session).
  3. Binds structlog contextvars + Sentry tags (reuses bind_tenant_context).
  4. Sets the RLS GUCs on the session (reuses rls.set_request_context) —
     no-op when DB_RLS_ENABLED is false.
  5. Runs the wrapped function; commits on success, rolls back on error.
  6. ALWAYS clears the structlog + Sentry context on exit, so the
     long-lived worker process never leaks one tenant's tags into the
     next job.
"""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable

import structlog

from aicmo.db import rls as _rls
from aicmo.db.session import SessionLocal
from aicmo.observability import bind_tenant_context, clear_tenant_context
from aicmo.queue.enqueue import TENANT_KW, TenantEnvelope

log = structlog.get_logger()


def tenant_job(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(fn)
    async def _wrapper(ctx: dict, *args: Any, **kwargs: Any) -> Any:
        raw = kwargs.pop(TENANT_KW, None)
        if raw is None:
            # Fail loud: an un-enveloped job would run with no tenant
            # scope. Never silently proceed.
            raise RuntimeError(
                f"job {fn.__name__!r} enqueued without a tenant envelope — "
                "use enqueue_tenant_job, never raw enqueue_job"
            )
        envelope = TenantEnvelope.from_payload(raw)

        structlog.contextvars.bind_contextvars(
            user_uuid=envelope.user_uuid,
            organization_id=envelope.organization_id,
            brand_id=envelope.brand_id,
            role_slugs=sorted(envelope.role_slugs),
            job=fn.__name__,
        )
        bind_tenant_context(
            user_uuid=envelope.user_id_uuid(),
            organization_id=envelope.org_uuid(),
            brand_id=envelope.brand_uuid(),
            role_slugs=sorted(envelope.role_slugs),
        )

        try:
            async with SessionLocal() as session:
                # Establish org-scoped RLS context on the job's own
                # transaction (no-op when DB_RLS_ENABLED is false).
                await _rls.set_request_context(
                    session,
                    organization_id=envelope.org_uuid(),
                    user_uuid=envelope.user_id_uuid(),
                )
                try:
                    result = await fn(ctx, session, envelope, *args, **kwargs)
                    await session.commit()
                    return result
                except Exception as exc:
                    await session.rollback()
                    log.warning("jobs.failed", job=fn.__name__)
                    # P0-4: surface worker job failures to Sentry + Slack.
                    from aicmo.observability.alerts import alert_job_failure

                    await alert_job_failure(fn.__name__, exc)
                    raise
        finally:
            # Critical: scrub tenant tags so the next job on this worker
            # starts clean.
            structlog.contextvars.clear_contextvars()
            clear_tenant_context()

    return _wrapper
