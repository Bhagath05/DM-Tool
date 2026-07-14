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


def resolve_effects(pairs: list[tuple[str, str]]) -> frozenset[str]:
    """Merge (slug, effect) pairs from every role a member holds into the
    effective granted set (Phase 6.6 ALLOW/DENY/INHERIT engine).

    - A permission is granted iff at least one role ALLOWs it AND no role
      explicitly DENYs it — an explicit DENY on any role overrides ALLOW.
    - INHERIT is represented by the absence of a pair (no override) and never
      grants on its own.
    Backward compatible: with only 'allow' rows (the pre-6.6 state) this returns
    the same union the old query produced.
    """
    allowed: set[str] = set()
    denied: set[str] = set()
    for slug, effect in pairs:
        (denied if effect == "deny" else allowed).add(slug)
    return frozenset(allowed - denied)


async def compute_permissions_for_member(
    session: AsyncSession, member_id: uuid.UUID
) -> frozenset[str]:
    """Return the effective permission slugs across every role assigned to this
    member, honouring ALLOW / DENY (explicit DENY wins). Empty set if the member
    has no roles (a data bug — every active member gets at least one role)."""
    stmt = (
        select(Permission.slug, RolePermission.effect)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .where(MemberRole.member_id == member_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return resolve_effects([(slug, effect) for slug, effect in rows])


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
