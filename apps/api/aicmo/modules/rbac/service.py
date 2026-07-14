"""RBAC service — roles + permissions read + custom-role management.

Custom roles are scoped to an organization (`roles.organization_id` set).
System roles are seeded once and shared (`organization_id IS NULL`).

The permission editor / role builder UI is out of S1.0 scope, but the
backend supports it today so adding the UI is purely additive.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.audit.models import AuditEvent
from aicmo.modules.orgs.models import MemberRole, OrganizationMember
from aicmo.modules.rbac.models import Permission, Role, RolePermission
from aicmo.modules.rbac.schemas import (
    PermissionResponse,
    RoleAuditEvent,
    RoleCreate,
    RoleDuplicate,
    RoleReorder,
    RoleResponse,
    RoleUpdate,
)
from aicmo.modules.users.models import User

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Permissions
# ---------------------------------------------------------------------


async def list_permissions(
    session: AsyncSession,
) -> list[PermissionResponse]:
    """Returns the full permission catalogue. Same for every org."""
    rows = (
        (await session.execute(select(Permission).order_by(Permission.category, Permission.slug)))
        .scalars()
        .all()
    )
    return [PermissionResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------
#  Roles
# ---------------------------------------------------------------------


async def list_roles(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    include_system: bool = True,
) -> list[RoleResponse]:
    """Return roles available to this org: all system roles + the org's
    custom roles. Each carries its permission slug list inlined.
    """
    stmt = select(Role)
    if include_system:
        stmt = stmt.where(
            or_(
                Role.organization_id == organization_id,
                Role.organization_id.is_(None),
            )
        )
    else:
        stmt = stmt.where(Role.organization_id == organization_id)
    # Highest priority first (hierarchy), then alphabetical for ties.
    stmt = stmt.order_by(Role.priority.desc(), Role.slug)
    roles = (await session.execute(stmt)).scalars().all()

    return [await _role_to_response(session, r) for r in roles]


async def get_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
) -> RoleResponse:
    row = await session.get(Role, role_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if row.organization_id is not None and row.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return await _role_to_response(session, row)


async def create_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: RoleCreate,
) -> RoleResponse:
    """Create a custom org-scoped role with the given permission slugs.

    Slug uniqueness is enforced per-org by the partial unique index in
    migration 0014.
    """
    # A permission may not be both allowed and denied.
    overlap = set(payload.permission_slugs) & set(payload.deny_slugs)
    if overlap:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Permission(s) both allowed and denied: {', '.join(sorted(overlap))}",
        )
    allow_ids = await _resolve_permission_ids(session, payload.permission_slugs)
    deny_ids = await _resolve_permission_ids(session, payload.deny_slugs)

    row = Role(
        organization_id=organization_id,
        slug=payload.slug,
        name=payload.name.strip(),
        description=payload.description,
        is_system=False,
        priority=payload.priority,
        color=payload.color,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Role slug '{payload.slug}' already exists in this org"
        ) from e

    # Assign permissions with their effect (ALLOW / DENY).
    for pid in allow_ids:
        session.add(RolePermission(role_id=row.id, permission_id=pid, effect="allow"))
    for pid in deny_ids:
        session.add(RolePermission(role_id=row.id, permission_id=pid, effect="deny"))
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="role.created",
        target_type="role",
        target_id=row.id,
        after={
            "slug": row.slug,
            "name": row.name,
            "permission_slugs": payload.permission_slugs,
            "deny_slugs": payload.deny_slugs,
        },
    )

    return await get_role(session, organization_id=organization_id, role_id=row.id)


async def update_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: RoleUpdate,
) -> RoleResponse:
    row = await session.get(Role, role_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if row.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "System roles cannot be modified")
    if row.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")

    before_allow, before_deny = await _effects_for_role(session, row.id)
    before = {
        "name": row.name,
        "description": row.description,
        "priority": row.priority,
        "color": row.color,
        "permission_slugs": sorted(before_allow),
        "deny_slugs": sorted(before_deny),
    }

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description
    if payload.priority is not None:
        row.priority = payload.priority
    # color: absent → unchanged; "" → clear; value → set.
    if "color" in payload.model_fields_set:
        row.color = payload.color or None

    if payload.permission_slugs is not None or payload.deny_slugs is not None:
        # Desired effect per slug. Whichever list is omitted keeps its
        # current state, so a partial (allow-only) update never silently
        # wipes existing denies.
        desired_allow = (
            set(payload.permission_slugs)
            if payload.permission_slugs is not None
            else set(before_allow)
        )
        desired_deny = (
            set(payload.deny_slugs) if payload.deny_slugs is not None else set(before_deny)
        )
        overlap = desired_allow & desired_deny
        if overlap:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Permission(s) both allowed and denied: {', '.join(sorted(overlap))}",
            )
        # Map desired slug → effect, then reconcile RolePermission rows.
        desired: dict[uuid.UUID, str] = {}
        for pid in await _resolve_permission_ids(session, sorted(desired_allow)):
            desired[pid] = "allow"
        for pid in await _resolve_permission_ids(session, sorted(desired_deny)):
            desired[pid] = "deny"

        current = (
            (await session.execute(select(RolePermission).where(RolePermission.role_id == row.id)))
            .scalars()
            .all()
        )
        current_by_pid = {rp.permission_id: rp for rp in current}
        for pid, rp in current_by_pid.items():
            if pid not in desired:
                await session.delete(rp)
            elif rp.effect != desired[pid]:
                rp.effect = desired[pid]
        for pid, effect in desired.items():
            if pid not in current_by_pid:
                session.add(RolePermission(role_id=row.id, permission_id=pid, effect=effect))

    await session.flush()
    after_allow, after_deny = await _effects_for_role(session, row.id)

    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="role.updated",
        target_type="role",
        target_id=row.id,
        before=before,
        after={
            "name": row.name,
            "description": row.description,
            "priority": row.priority,
            "color": row.color,
            "permission_slugs": sorted(after_allow),
            "deny_slugs": sorted(after_deny),
        },
    )
    return await get_role(session, organization_id=organization_id, role_id=row.id)


async def delete_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
) -> None:
    row = await session.get(Role, role_id)
    if row is None or row.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if row.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "System roles cannot be deleted")

    await session.delete(row)
    await session.flush()
    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="role.deleted",
        target_type="role",
        target_id=role_id,
        before={"slug": row.slug, "name": row.name},
    )


async def reorder_roles(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: RoleReorder,
) -> list[RoleResponse]:
    """Apply a drag-to-reorder gesture: set `priority` on the org's custom
    roles. System roles are skipped — their priority is global and fixed —
    so a payload that includes them simply leaves them where they are."""
    changed: list[str] = []
    for item in payload.items:
        row = await session.get(Role, item.role_id)
        if row is None:
            continue
        # Only reprice this org's own custom roles.
        if row.is_system or row.organization_id != organization_id:
            continue
        if row.priority != item.priority:
            row.priority = item.priority
            changed.append(row.slug)
    if changed:
        await session.flush()
        await audit_service.record(
            session,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="role.reordered",
            target_type="role",
            after={"reordered": sorted(changed)},
        )
    return await list_roles(session, organization_id=organization_id, include_system=True)


async def duplicate_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    source_role_id: uuid.UUID,
    payload: RoleDuplicate,
) -> RoleResponse:
    """Clone any visible role (system or this org's custom) into a NEW
    custom org role, copying its ALLOW + DENY grants, color, and priority."""
    source = await session.get(Role, source_role_id)
    if source is None or (
        source.organization_id is not None and source.organization_id != organization_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")

    allow, deny = await _effects_for_role(session, source.id)
    clone = await create_role(
        session,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        payload=RoleCreate(
            slug=payload.slug,
            name=payload.name,
            description=source.description,
            priority=source.priority or 0,
            color=source.color,
            permission_slugs=sorted(allow),
            deny_slugs=sorted(deny),
        ),
    )
    return clone


async def list_role_audit(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    role_slug: str,
    limit: int = 100,
) -> list[RoleAuditEvent]:
    """Read the existing audit trail for one role: direct role.* mutations
    (target_id == role_id) plus member.role_assigned / member.role_removed
    events that reference this role's slug. Newest first."""
    slug_match = or_(
        AuditEvent.after["role_slug"].astext == role_slug,
        AuditEvent.before["role_slug"].astext == role_slug,
    )
    stmt = (
        select(AuditEvent, User)
        .join(User, User.id == AuditEvent.actor_user_id, isouter=True)
        .where(
            AuditEvent.organization_id == organization_id,
            or_(
                and_(
                    AuditEvent.target_type == "role",
                    AuditEvent.target_id == role_id,
                ),
                and_(
                    AuditEvent.action.in_(("member.role_assigned", "member.role_removed")),
                    slug_match,
                ),
            ),
        )
        .order_by(AuditEvent.occurred_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    out: list[RoleAuditEvent] = []
    for evt, user in rows:
        out.append(
            RoleAuditEvent(
                id=evt.id,
                action=evt.action,
                actor_user_id=evt.actor_user_id,
                actor_email=user.email if user else None,
                actor_name=(user.display_name if user else None),
                target_type=evt.target_type,
                target_id=evt.target_id,
                summary=_audit_summary(evt),
                occurred_at=evt.occurred_at,
            )
        )
    return out


def _audit_summary(evt: AuditEvent) -> str:
    """A short human line for the audit row (the UI renders this verbatim)."""
    verb = {
        "role.created": "Role created",
        "role.updated": "Role updated",
        "role.deleted": "Role deleted",
        "role.reordered": "Roles reordered",
        "member.role_assigned": "Assigned to a member",
        "member.role_removed": "Removed from a member",
    }.get(evt.action, evt.action)
    return verb


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


async def _permission_slugs_for_role(session: AsyncSession, role_id: uuid.UUID) -> frozenset[str]:
    """The ALLOW set (backward-compatible — this is what every existing
    caller means by "the role's permissions")."""
    allow, _deny = await _effects_for_role(session, role_id)
    return allow


async def _effects_for_role(
    session: AsyncSession, role_id: uuid.UUID
) -> tuple[frozenset[str], frozenset[str]]:
    """Return (allow_slugs, deny_slugs) for a role. INHERIT is the absence
    of a slug from both sets."""
    rows = (
        await session.execute(
            select(Permission.slug, RolePermission.effect)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
    ).all()
    allow = {slug for slug, effect in rows if effect != "deny"}
    deny = {slug for slug, effect in rows if effect == "deny"}
    return frozenset(allow), frozenset(deny)


async def _member_count_for_role(session: AsyncSession, role_id: uuid.UUID) -> int:
    """How many active members currently hold this role."""
    stmt = (
        select(func.count(MemberRole.member_id.distinct()))
        .join(
            OrganizationMember,
            OrganizationMember.id == MemberRole.member_id,
        )
        .where(
            MemberRole.role_id == role_id,
            OrganizationMember.status == "active",
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _role_to_response(session: AsyncSession, row: Role) -> RoleResponse:
    allow, deny = await _effects_for_role(session, row.id)
    return RoleResponse(
        id=row.id,
        organization_id=row.organization_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        is_system=row.is_system,
        priority=row.priority or 0,
        color=row.color,
        permission_slugs=sorted(allow),
        deny_slugs=sorted(deny),
        member_count=await _member_count_for_role(session, row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _resolve_permission_ids(session: AsyncSession, slugs: list[str]) -> list[uuid.UUID]:
    """Map permission slugs to ids. 400 on any unknown slug."""
    if not slugs:
        return []
    rows = (
        await session.execute(
            select(Permission.id, Permission.slug).where(Permission.slug.in_(slugs))
        )
    ).all()
    found = {row[1]: row[0] for row in rows}
    missing = [s for s in slugs if s not in found]
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown permission slug(s): {', '.join(missing)}",
        )
    return [found[s] for s in slugs]
