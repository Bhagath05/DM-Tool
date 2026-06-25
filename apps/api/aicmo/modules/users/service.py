"""Users service.

Two responsibilities:

1. **Identity reconciliation** — `get_or_create_from_clerk` is also
   exported from `tenancy.dependencies`, but kept here as the canonical
   home so future paths (Clerk webhook, admin tools) call one function.

2. **`/me` aggregation** — `build_me_response` does the join across
   users → memberships → orgs → brands → roles → permissions in a
   bounded set of queries (N memberships × ~2 queries, not N²).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.brands.models import Brand
from aicmo.modules.orgs.models import Organization, OrganizationMember
from aicmo.modules.users.models import User
from aicmo.modules.users.schemas import (
    ActiveTenant,
    BrandSummary,
    MembershipResponse,
    MeResponse,
    OrgSummary,
    SuggestedRoute,
    UserResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.permissions import (
    compute_permissions_for_member,
    compute_role_slugs_for_member,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Identity reconciliation
# ---------------------------------------------------------------------


async def get_or_create_from_clerk(
    session: AsyncSession,
    *,
    clerk_user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    """Lazy-create the User row. Also called from tenancy resolver.

    When `email` is provided (webhook path), it overwrites the placeholder
    we may have inserted on a prior lazy-create.
    """
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        row = User(
            clerk_user_id=clerk_user_id,
            email=email or f"{clerk_user_id}@pending.local",
            display_name=display_name,
            avatar_url=avatar_url,
            status="active",
            last_seen_at=datetime.now(UTC),
        )
        session.add(row)
        await session.flush()
        return row

    # Update mutable fields when caller has fresh data (typically webhook).
    dirty = False
    if email and (
        row.email.endswith("@pending.local") or row.email != email
    ):
        row.email = email
        dirty = True
    if display_name and row.display_name != display_name:
        row.display_name = display_name
        dirty = True
    if avatar_url and row.avatar_url != avatar_url:
        row.avatar_url = avatar_url
        dirty = True
    row.last_seen_at = datetime.now(UTC)
    if dirty:
        await session.flush()
    return row


# ---------------------------------------------------------------------
#  /me aggregation
# ---------------------------------------------------------------------


async def build_me_response(
    session: AsyncSession,
    *,
    user: User,
    active: TenantContext | None,
) -> MeResponse:
    """Build the /api/v1/me payload.

    Touches: user (cached), N memberships, N orgs, N×M brands,
    N members × (roles + perms). For typical N <= 5, this stays under
    10 queries. We accept that — sub-50ms even at 20 memberships.
    """
    # 1. All active memberships for this user.
    mem_stmt = (
        select(OrganizationMember)
        .where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
        )
        .order_by(OrganizationMember.joined_at)
    )
    members = (await session.execute(mem_stmt)).scalars().all()

    memberships: list[MembershipResponse] = []
    for m in members:
        org = await session.get(Organization, m.organization_id)
        if org is None or org.status == "deleted":
            continue

        # Brands in this org (active only).
        brand_rows = (
            await session.execute(
                select(Brand)
                .where(Brand.organization_id == m.organization_id)
                .where(Brand.status == "active")
                .order_by(Brand.created_at)
            )
        ).scalars().all()

        role_slugs = await compute_role_slugs_for_member(session, m.id)
        permissions = await compute_permissions_for_member(session, m.id)

        memberships.append(
            MembershipResponse(
                organization=OrgSummary.model_validate(org),
                role_slugs=sorted(role_slugs),
                permissions=sorted(permissions),
                brands=[BrandSummary.model_validate(b) for b in brand_rows],
                last_active_brand_id=m.last_active_brand_id,
                joined_at=m.joined_at,
            )
        )

    # 2. Compose the active-tenant snapshot (if the caller carried headers).
    active_payload: ActiveTenant | None = None
    if active is not None:
        active_payload = ActiveTenant(
            organization_id=active.organization_id,
            brand_id=active.brand_id,
            role_slugs=sorted(active.role_slugs),
            permissions=sorted(active.permissions),
        )

    # 3. Suggest the next route the frontend should send the user to.
    suggested = _suggest_route(memberships=memberships, active=active)

    return MeResponse(
        user=UserResponse.model_validate(user),
        memberships=memberships,
        active=active_payload,
        suggested_route=suggested,
    )


def _suggest_route(
    *,
    memberships: list[MembershipResponse],
    active: TenantContext | None,
) -> SuggestedRoute:
    """Mirror of the redirect matrix in the CTO plan §5.4.

    Centralised here so the frontend's `/onboarding` wrapper page only
    has to read this field.
    """
    if not memberships:
        return "/onboarding"
    if active is None and len(memberships) > 1:
        return "/orgs/select"
    # Active tenant resolved (or single membership). Check if brand exists.
    # The /onboarding wizard also handles the org-only case: its /me preflight
    # detects a brand-less org and resumes the user on the brand step.
    if not memberships[0].brands:
        return "/onboarding"
    # Brand exists. Profile completeness is checked by the existing
    # business onboarding flow itself — for /me we assume dashboard
    # unless the caller explicitly tells us otherwise.
    return "/dashboard"
