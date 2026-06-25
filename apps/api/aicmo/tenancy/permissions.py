"""Permission resolver — computes the set of permission slugs a member
has across all their assigned roles.

Why one place: the policy is (member → roles → permissions). We resolve
the slug set once per request and cache via FastAPI's dependency cache,
so a route hitting `require_permission` 5x in its dep tree only runs the
query once.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.orgs.models import MemberRole
from aicmo.modules.rbac.models import Permission, Role, RolePermission


async def compute_permissions_for_member(
    session: AsyncSession, member_id: uuid.UUID
) -> frozenset[str]:
    """Return the union of permission slugs across every role assigned
    to this member. Empty set if the member has no roles (which would
    be a data bug — every active member gets at least one role)."""
    stmt = (
        select(Permission.slug)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .where(MemberRole.member_id == member_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return frozenset(rows)


async def compute_role_slugs_for_member(
    session: AsyncSession, member_id: uuid.UUID
) -> frozenset[str]:
    """Return every role slug assigned to this member. Used by the frontend
    to render "Owner" / "Admin" / etc badges without re-querying."""
    stmt = (
        select(Role.slug)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .where(MemberRole.member_id == member_id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return frozenset(rows)
