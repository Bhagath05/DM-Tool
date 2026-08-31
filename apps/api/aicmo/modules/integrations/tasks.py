"""ARQ tasks for the integrations module — automated marketing-metrics collection.

`collect_metrics_cron` schedules the *existing* caller-initiated
`integrations.service.sync` for every ACTIVE connection that is due for a
refresh. It adds NO new metrics model, provider abstraction, token store,
queue, or OAuth flow — it only automates what already exists:

    ACTIVE IntegrationConnection
        → service.sync (decrypt token → provider.sync → upsert ConnectorMetric)
        → last_sync_at cursor advanced + IntegrationEvent recorded

Design guarantees:
- **Failure isolation:** each connection runs in its own DB session; one
  provider/account failure never aborts the run (never re-raises).
- **Idempotent + incremental:** dedup comes from the existing
  `advisor.connectors.upsert_metric` key (brand, provider, metric_key,
  period_end); `last_sync_at` is the cursor so fresh connections are skipped.
- **No secrets in logs:** `service.sync` logs metadata only; this module logs
  connection ids, provider slugs, and exception *type names* — never tokens,
  refresh tokens, client secrets, authorization codes, or provider blobs.
- **Tenant isolation preserved:** each sync is scoped to the connection's own
  org/brand; metrics are written to that brand only.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select

from aicmo.db.session import SessionLocal
from aicmo.modules.integrations import service as integrations_service
from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# How stale a connection's last_sync_at must be before we re-collect. Paired
# with the 6-hourly cron in queue/worker.py so each run picks up the previous
# run's connections without hammering provider APIs.
_STALE_AFTER = timedelta(hours=5)

# Bounded concurrency so a large tenant base can't fan out into a provider-API
# stampede. Each unit still runs in its own DB session.
_MAX_CONCURRENCY = 5


def _system_tenant(conn: IntegrationConnection) -> TenantContext:
    """A context scoped to the connection's OWN org/brand.

    `user_uuid=None` marks this as a system (non-user) operation, so
    `service.sync` skips the per-user audit write — `audit_logs.actor_user_id`
    is a NOT-NULL FK to `users`, so a synthetic id would violate it. The
    ownership load uses org_id/brand_id only, so tenant isolation holds: each
    sync writes metrics to its own brand and cannot touch another tenant.
    """
    return TenantContext(
        user_id="",  # system — no Clerk subject
        user_uuid=None,  # type: ignore[arg-type]  # falsy → service.sync skips the per-user audit (FK-safe)
        organization_id=conn.organization_id,
        brand_id=conn.brand_id,
        member_id=uuid.UUID(int=0),  # unused by sync; placeholder for the frozen dataclass
    )


async def _due_connection_ids(session, *, stale_before: datetime) -> list[uuid.UUID]:
    """ACTIVE connections that have never synced OR synced before `stale_before`."""
    rows = await session.execute(
        select(IntegrationConnection.id).where(
            IntegrationConnection.state == "ACTIVE",
            or_(
                IntegrationConnection.last_sync_at.is_(None),
                IntegrationConnection.last_sync_at < stale_before,
            ),
        )
    )
    return list(rows.scalars().all())


async def _sync_one(connection_id: uuid.UUID) -> bool:
    """Sync a single connection in its own session.

    Returns True on success, False on skip/failure — never raises, so one
    account can't abort the run. `service.sync` commits success internally and
    `_fail_to_error` commits the ERROR state, so no commit is needed here.
    """
    async with SessionLocal() as session:
        conn = await session.get(IntegrationConnection, connection_id)
        if conn is None or conn.state != "ACTIVE":
            return False
        provider = conn.provider_slug
        try:
            await integrations_service.sync(
                session, tenant=_system_tenant(conn), connection_id=conn.id
            )
            return True
        except Exception as e:  # isolate — never abort the run for one account
            # service.sync already persisted a safe IntegrationEvent + ERROR
            # state. Log names/types ONLY — never tokens, secrets, or blobs.
            log.warning(
                "integrations.collect_metrics.connection_failed",
                connection_id=str(connection_id),
                provider=provider,
                error_type=type(e).__name__,
            )
            return False


async def collect_metrics_cron(ctx: dict) -> dict:
    """Scheduled automatic metrics collection across all tenants/accounts.

    Idempotent + incremental by construction (see module docstring). Safe to
    run repeatedly. Returns a small summary for observability."""
    stale_before = datetime.now(UTC) - _STALE_AFTER
    async with SessionLocal() as session:
        due = await _due_connection_ids(session, stale_before=stale_before)

    if not due:
        log.info("integrations.collect_metrics.done", due=0, synced=0, failed=0)
        return {"due": 0, "synced": 0, "failed": 0}

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _guarded(cid: uuid.UUID) -> bool:
        async with sem:
            return await _sync_one(cid)

    results = await asyncio.gather(*[_guarded(cid) for cid in due])
    synced = sum(1 for r in results if r)
    failed = len(results) - synced
    log.info(
        "integrations.collect_metrics.done",
        due=len(due),
        synced=synced,
        failed=failed,
    )
    return {"due": len(due), "synced": synced, "failed": failed}
