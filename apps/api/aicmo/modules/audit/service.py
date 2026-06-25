"""Audit writer.

One public function: `record(...)`. Called from every service mutation
that changes RBAC, membership, or tenant configuration.

Write semantics:
- Best-effort. Audit failures NEVER block the user's action.
- Same transaction as the caller — if the caller rolls back, the audit
  row rolls back too (this is correct: we don't want audit-of-event-that-
  didn't-happen).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit.models import AuditEvent

log = structlog.get_logger()


async def record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: str,
    brand_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append one audit row. Never raises.

    Action slugs follow `entity.verb` convention:
        organization.created, organization.updated, organization.deleted
        brand.created, brand.updated, brand.archived
        member.invited, member.removed, member.role_assigned, member.role_removed
        role.created, role.updated, role.deleted
    """
    try:
        evt = AuditEvent(
            organization_id=organization_id,
            brand_id=brand_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata or {},
        )
        session.add(evt)
        await session.flush()
    except Exception as e:  # noqa: BLE001 — audit MUST NOT block the action
        log.warning(
            "audit.write_failed",
            action=action,
            error=str(e),
            organization_id=str(organization_id),
        )
