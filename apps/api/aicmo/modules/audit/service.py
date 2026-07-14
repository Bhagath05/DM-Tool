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
from datetime import datetime

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit.models import AuditEvent
from aicmo.modules.audit.schemas import AuditEventRead
from aicmo.modules.users.models import User

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


# ---------------------------------------------------------------------
#  Read (org-wide audit log — Phase 6.6 Slice 4)
# ---------------------------------------------------------------------


async def list_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actions: list[str] | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[AuditEventRead]:
    """Org-scoped audit trail, newest first, with the actor's email/name
    joined in. All filters are optional and AND-combined. `search` is a
    case-insensitive match over action + actor email + target type.

    Read-only — never writes. Callers gate this behind `organization.manage`.
    """
    stmt = (
        select(AuditEvent, User)
        .join(User, User.id == AuditEvent.actor_user_id, isouter=True)
        .where(AuditEvent.organization_id == organization_id)
    )
    if actions:
        stmt = stmt.where(AuditEvent.action.in_(actions))
    if actor_user_id is not None:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
    if since is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= until)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AuditEvent.action).like(like),
                func.lower(AuditEvent.target_type).like(like),
                func.lower(User.email).like(like),
            )
        )
    stmt = stmt.order_by(AuditEvent.occurred_at.desc()).limit(min(max(limit, 1), 1000))

    rows = (await session.execute(stmt)).all()
    return [
        AuditEventRead(
            id=evt.id,
            action=evt.action,
            actor_user_id=evt.actor_user_id,
            actor_email=user.email if user else None,
            actor_name=(user.display_name if user else None),
            target_type=evt.target_type,
            target_id=evt.target_id,
            brand_id=evt.brand_id,
            before=evt.before,
            after=evt.after,
            occurred_at=evt.occurred_at,
        )
        for evt, user in rows
    ]


async def distinct_actions(session: AsyncSession, *, organization_id: uuid.UUID) -> list[str]:
    """Every action slug present in this org's log — powers the UI's
    action filter dropdown without a hardcoded list."""
    rows = (
        (
            await session.execute(
                select(AuditEvent.action)
                .where(AuditEvent.organization_id == organization_id)
                .distinct()
                .order_by(AuditEvent.action)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
