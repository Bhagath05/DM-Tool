"""Tenant-aware job enqueue — Phase 0.

The ONLY sanctioned way to enqueue a background job. Captures the
caller's tenant scope into a server-authored envelope and serializes it
into the job payload, so the worker can restore the exact same
structlog / Sentry / RLS context at execution time.

Trust model (identical to the request resolver): the `_TenantEnvelope`
is built from a validated `TenantContext` on the server. It is NEVER
accepted from client input. The Redis payload is trusted infrastructure,
same as the database.

Usage (from a request handler or service):

    from aicmo.queue.enqueue import enqueue_tenant_job

    await enqueue_tenant_job(
        pool, "autopilot_weekly", brief_id, tenant=tenant
    )

`pool` is the ArqRedis pool (request handlers get it via
`get_arq_pool`). The job function on the worker side must be decorated
with `@tenant_job` (see queue/context.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from aicmo.config import get_settings
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# The kwarg key the envelope rides in. Underscored so it never collides
# with a job's real arguments.
TENANT_KW = "_tenant"


@dataclass(frozen=True, slots=True)
class TenantEnvelope:
    """Serializable snapshot of the tenant scope, carried through Redis.

    Only the fields a background job legitimately needs to re-establish
    isolation. Permissions are intentionally omitted — a job runs a
    fixed, pre-authorized unit of work; it does not make per-permission
    branching decisions (the enqueue site already gated on permission).
    """

    user_uuid: str
    organization_id: str
    brand_id: str | None
    role_slugs: list[str]

    @classmethod
    def from_context(cls, tenant: TenantContext) -> "TenantEnvelope":
        return cls(
            user_uuid=str(tenant.user_uuid),
            organization_id=str(tenant.organization_id),
            brand_id=str(tenant.brand_id) if tenant.brand_id else None,
            role_slugs=sorted(tenant.role_slugs),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_uuid": self.user_uuid,
            "organization_id": self.organization_id,
            "brand_id": self.brand_id,
            "role_slugs": list(self.role_slugs),
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "TenantEnvelope":
        return cls(
            user_uuid=data["user_uuid"],
            organization_id=data["organization_id"],
            brand_id=data.get("brand_id"),
            role_slugs=list(data.get("role_slugs") or []),
        )

    # Typed accessors used by the worker-side decorator.
    def org_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.organization_id)

    def user_id_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.user_uuid)

    def brand_uuid(self) -> uuid.UUID | None:
        return uuid.UUID(self.brand_id) if self.brand_id else None


async def enqueue_tenant_job(
    pool: Any,
    function_name: str,
    *args: Any,
    tenant: TenantContext,
    **kwargs: Any,
):
    """Enqueue `function_name` with the tenant envelope attached.

    Returns the arq Job, or None when jobs are disabled (kill switch) or
    no pool is available — callers must treat enqueue as best-effort and
    never depend on a return value for correctness.
    """
    settings = get_settings()
    if not settings.jobs_enabled:
        log.info("jobs.disabled.skip_enqueue", function=function_name)
        return None
    if pool is None:
        log.warning("jobs.no_pool.skip_enqueue", function=function_name)
        return None

    envelope = TenantEnvelope.from_context(tenant)
    kwargs[TENANT_KW] = envelope.to_payload()
    job = await pool.enqueue_job(function_name, *args, **kwargs)
    log.info(
        "jobs.enqueued",
        function=function_name,
        organization_id=envelope.organization_id,
        brand_id=envelope.brand_id,
    )
    return job
