"""FastAPI dependencies for tenant + permission resolution.

Usage:

    @router.post("/api/v1/ads/generate")
    async def generate(
        payload: GenerateAdRequest,
        tenant: TenantContext = Depends(require_permission("content.create")),
        session: AsyncSession = Depends(get_db),
    ): ...

require_tenant resolves the (user, org, brand, role, permissions) bundle.
require_permission composes require_tenant and asserts a specific slug.
"""

from __future__ import annotations

import uuid
from typing import Callable

import structlog
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.db import rls as _rls
from aicmo.db.session import get_db
from aicmo.modules.brands.models import Brand
from aicmo.modules.orgs.models import Organization, OrganizationMember
from aicmo.modules.users.service import get_or_create_from_clerk
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.exceptions import (
    BrandInactive,
    BrandNotInOrg,
    MissingTenant,
    NotAuthorized,
    OrganizationInactive,
    TenantMismatch,
)
from aicmo.tenancy.headers import parse_brand_header, parse_org_header
from aicmo.tenancy.permissions import (
    compute_permissions_for_member,
    compute_role_slugs_for_member,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  require_tenant
# ---------------------------------------------------------------------


def require_tenant(brand_optional: bool = False) -> Callable:
    """Factory. Returns a FastAPI dep that resolves TenantContext.

    `brand_optional=True` for org-level routes (members, billing,
    settings). When True, missing brand header is fine — we still try to
    resolve from the user's `last_active_brand_id` or single brand, but
    we don't 400 if none is found.
    """

    async def _dep(
        request: Request,
        auth: AuthContext = Depends(require_user),
        session: AsyncSession = Depends(get_db),
    ) -> TenantContext:
        # 0. RLS readiness — during resolution we read users/organizations
        # before the tenant context is known, so bypass RLS for the lookup
        # phase. We turn it OFF and set the real org/user GUCs in step 8,
        # before the request handler body runs. No-op when DB_RLS_ENABLED
        # is false (the default).
        await _rls.set_bypass(session, on=True)

        # 1. Lazy-create the User row. The webhook path also creates it,
        # but lazy-create is the safety net for race conditions and dev
        # environments without webhook tunnels.
        user = await get_or_create_from_clerk(
            session,
            clerk_user_id=auth.user_id,
            email=auth.email,
            display_name=auth.display_name,
            avatar_url=auth.avatar_url,
        )

        # 2. Resolve the active organization.
        org_id = parse_org_header(request)
        if org_id is None:
            # Auto-resolve when the user has exactly one active membership.
            single = await _single_active_membership_org(
                session, user_id=user.id
            )
            if single is None:
                raise MissingTenant(
                    detail="X-Organization-Id header required (user has 0 or multiple memberships)"
                )
            org_id = single

        # 3. Validate the user is a member of that org.
        member = await _load_active_member(
            session, user_id=user.id, org_id=org_id
        )
        if member is None:
            raise TenantMismatch()

        # 4. Validate the org is active.
        org = await session.get(Organization, org_id)
        if org is None or org.status != "active":
            raise OrganizationInactive()

        # 5. Resolve the active brand.
        brand_id = parse_brand_header(request)
        if brand_id is None:
            # Sticky brand from membership, else only-brand auto-resolve.
            brand_id = member.last_active_brand_id
        if brand_id is None:
            brand_id = await _only_active_brand(session, org_id=org_id)

        brand: Brand | None = None
        if brand_id is not None:
            brand = await session.get(Brand, brand_id)
            if brand is None or brand.organization_id != org_id:
                raise BrandNotInOrg()
            if brand.status != "active":
                raise BrandInactive()

        if brand_id is None and not brand_optional:
            raise MissingTenant(
                detail="X-Brand-Id header required (org has 0 or multiple brands)"
            )

        # 6. Compute permissions + role slugs.
        permissions = await compute_permissions_for_member(
            session, member_id=member.id
        )
        role_slugs = await compute_role_slugs_for_member(
            session, member_id=member.id
        )

        # 7. Best-effort: persist last_active_brand_id if it changed.
        # Not in the request transaction — the next request will use
        # whatever value we land on, no correctness issue if this fails.
        if brand_id is not None and member.last_active_brand_id != brand_id:
            member.last_active_brand_id = brand_id
            try:
                await session.flush()
            except Exception:  # noqa: BLE001
                pass  # purely cosmetic, never break the request

        # 8. Bind tenant context to structlog so every downstream log
        # line in this request carries org/brand for triage.
        structlog.contextvars.bind_contextvars(
            user_uuid=str(user.id),
            organization_id=str(org_id),
            brand_id=str(brand_id) if brand_id else None,
            role_slugs=sorted(role_slugs),
        )

        # Mirror the same context into Sentry so any exception raised
        # downstream is tagged with user/org/brand for triage. No-op when
        # Sentry isn't initialised.
        from aicmo.observability import bind_tenant_context as _bind_sentry

        _bind_sentry(
            user_uuid=user.id,
            organization_id=org_id,
            brand_id=brand_id,
            role_slugs=sorted(role_slugs),
        )

        # 9. RLS readiness — resolution is done. Switch bypass OFF and pin
        # the per-request org/user GUCs so the handler body runs under
        # org-scoped RLS. No-op when DB_RLS_ENABLED is false.
        await _rls.set_request_context(
            session, organization_id=org_id, user_uuid=user.id
        )

        return TenantContext(
            user_id=auth.user_id,
            user_uuid=user.id,
            organization_id=org_id,
            brand_id=brand_id,
            member_id=member.id,
            role_slugs=role_slugs,
            permissions=permissions,
        )

    return _dep


# Pre-baked common variants so route signatures stay clean.
RequireTenant = Depends(require_tenant())
RequireTenantOrgOnly = Depends(require_tenant(brand_optional=True))


# ---------------------------------------------------------------------
#  require_permission
# ---------------------------------------------------------------------


def require_permission(
    slug: str, *, brand_optional: bool = False
) -> Callable:
    """Asserts the resolved tenant carries the given permission slug.

    `brand_optional=True` for org-level permission checks (e.g.
    `team.manage`, `billing.manage`). Default is brand-required.
    """

    tenant_dep = require_tenant(brand_optional=brand_optional)

    async def _dep(
        tenant: TenantContext = Depends(tenant_dep),
    ) -> TenantContext:
        if slug not in tenant.permissions:
            log.warning(
                "tenancy.not_authorized",
                action=slug,
                user_uuid=str(tenant.user_uuid),
                org_id=str(tenant.organization_id),
                roles=sorted(tenant.role_slugs),
            )
            raise NotAuthorized(
                action=slug,
                role=next(iter(tenant.role_slugs), None),
            )
        return tenant

    return _dep


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


async def _single_active_membership_org(
    session: AsyncSession, *, user_id: uuid.UUID
) -> uuid.UUID | None:
    """If the user has exactly one active membership, return its org_id.
    Else None (caller must require an explicit header)."""
    stmt = select(OrganizationMember.organization_id).where(
        OrganizationMember.user_id == user_id,
        OrganizationMember.status == "active",
    )
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) == 1:
        return rows[0]
    return None


async def _load_active_member(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> OrganizationMember | None:
    stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == user_id,
        OrganizationMember.organization_id == org_id,
        OrganizationMember.status == "active",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _only_active_brand(
    session: AsyncSession, *, org_id: uuid.UUID
) -> uuid.UUID | None:
    """If the org has exactly one active brand, return its id."""
    stmt = select(Brand.id).where(
        Brand.organization_id == org_id, Brand.status == "active"
    )
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) == 1:
        return rows[0]
    return None
