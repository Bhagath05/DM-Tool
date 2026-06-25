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
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.rbac.models import Permission, Role, RolePermission
from aicmo.modules.rbac.schemas import (
    PermissionResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Permissions
# ---------------------------------------------------------------------


async def list_permissions(
    session: AsyncSession,
) -> list[PermissionResponse]:
    """Returns the full permission catalogue. Same for every org."""
    rows = (
        await session.execute(
            select(Permission).order_by(Permission.category, Permission.slug)
        )
    ).scalars().all()
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
    stmt = stmt.order_by(Role.is_system.desc(), Role.slug)
    roles = (await session.execute(stmt)).scalars().all()

    out: list[RoleResponse] = []
    for r in roles:
        slugs = await _permission_slugs_for_role(session, r.id)
        out.append(
            RoleResponse(
                id=r.id,
                organization_id=r.organization_id,
                slug=r.slug,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
                permission_slugs=sorted(slugs),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


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
    slugs = await _permission_slugs_for_role(session, row.id)
    return RoleResponse(
        id=row.id,
        organization_id=row.organization_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        is_system=row.is_system,
        permission_slugs=sorted(slugs),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


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
    perm_ids = await _resolve_permission_ids(session, payload.permission_slugs)

    row = Role(
        organization_id=organization_id,
        slug=payload.slug,
        name=payload.name.strip(),
        description=payload.description,
        is_system=False,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as e:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Role slug '{payload.slug}' already exists in this org"
        ) from e

    # Assign permissions
    for pid in perm_ids:
        session.add(RolePermission(role_id=row.id, permission_id=pid))
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
        },
    )

    return await get_role(
        session, organization_id=organization_id, role_id=row.id
    )


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
        raise HTTPException(
            status.HTTP_409_CONFLICT, "System roles cannot be modified"
        )
    if row.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")

    before = {
        "name": row.name,
        "description": row.description,
        "permission_slugs": sorted(
            await _permission_slugs_for_role(session, row.id)
        ),
    }

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description

    if payload.permission_slugs is not None:
        # Diff-replace
        new_ids = set(
            await _resolve_permission_ids(session, payload.permission_slugs)
        )
        current = (
            await session.execute(
                select(RolePermission).where(RolePermission.role_id == row.id)
            )
        ).scalars().all()
        current_ids = {rp.permission_id for rp in current}
        for rp in current:
            if rp.permission_id not in new_ids:
                await session.delete(rp)
        for pid in new_ids - current_ids:
            session.add(RolePermission(role_id=row.id, permission_id=pid))

    await session.flush()
    after_slugs = sorted(await _permission_slugs_for_role(session, row.id))

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
            "permission_slugs": after_slugs,
        },
    )
    return await get_role(
        session, organization_id=organization_id, role_id=row.id
    )


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
        raise HTTPException(
            status.HTTP_409_CONFLICT, "System roles cannot be deleted"
        )

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


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


async def _permission_slugs_for_role(
    session: AsyncSession, role_id: uuid.UUID
) -> frozenset[str]:
    rows = (
        await session.execute(
            select(Permission.slug)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
    ).scalars().all()
    return frozenset(rows)


async def _resolve_permission_ids(
    session: AsyncSession, slugs: list[str]
) -> list[uuid.UUID]:
    """Map permission slugs to ids. 400 on any unknown slug."""
    if not slugs:
        return []
    rows = (
        await session.execute(
            select(Permission.id, Permission.slug).where(
                Permission.slug.in_(slugs)
            )
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
