"""Organizations + memberships HTTP surface."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.db.session import get_db
from aicmo.modules.orgs import service
from aicmo.modules.orgs.schemas import (
    MemberAssignRole,
    MemberList,
    MemberRoleUpdate,
    OnboardingWorkspacePayload,
    OnboardingWorkspaceResult,
    OrganizationAnalytics,
    OrganizationCreate,
    OrganizationCreateResult,
    OrganizationList,
    OrganizationProfileRead,
    OrganizationProfileUpdate,
    OrganizationResetResult,
    OrganizationResponse,
    OrganizationUpdate,
)
from aicmo.modules.users.service import get_or_create_from_clerk
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/orgs", tags=["orgs"])


# ---------------------------------------------------------------------
#  Org create + list (no tenant headers required — these RUN BEFORE
#  the user has a tenant context.)
# ---------------------------------------------------------------------


@router.post(
    "",
    response_model=OrganizationCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: OrganizationCreate,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> OrganizationCreateResult:
    """Atomic: user (lazy) → org → brand → membership → owner role.

    No permission check — any authenticated user can create an org.
    """
    user = await get_or_create_from_clerk(
        session, clerk_user_id=auth.user_id
    )
    result = await service.create_organization(
        session, actor_user=user, payload=payload
    )
    await session.commit()
    return result


@router.post(
    "/workspace",
    response_model=OnboardingWorkspaceResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_via_wizard(
    payload: OnboardingWorkspacePayload,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> OnboardingWorkspaceResult:
    """Single-shot onboarding wizard endpoint (W1-15).

    Transactional: user (lazy) + display_name + organization + brand +
    membership + owner role assignment, all in one TX. Any failure
    rolls back the whole thing.

    No tenant headers required — same as `POST /orgs` — because this
    runs BEFORE the user has a tenant context. Auth is required (Clerk
    JWT) but RBAC is not consulted; the operation grants the caller
    Owner on the newly-created org.
    """
    user = await get_or_create_from_clerk(
        session, clerk_user_id=auth.user_id
    )
    result = await service.create_workspace(
        session, actor_user=user, payload=payload
    )
    await session.commit()
    return result


@router.get("", response_model=OrganizationList)
async def list_my_orgs(
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> OrganizationList:
    """List orgs the caller is a member of. Used by the org switcher."""
    user = await get_or_create_from_clerk(
        session, clerk_user_id=auth.user_id
    )
    items = await service.list_user_orgs(session, user_id=user.id)
    await session.commit()
    return OrganizationList(items=items)


# ---------------------------------------------------------------------
#  Org-scoped routes (require_permission resolves tenant headers)
# ---------------------------------------------------------------------


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_one(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    _ensure_active_tenant(tenant, org_id)
    return await service.get_org(session, org_id=org_id)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_one(
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    _ensure_active_tenant(tenant, org_id)
    result = await service.update_org(
        session,
        actor_user_id=tenant.user_uuid,
        org_id=org_id,
        payload=payload,
    )
    await session.commit()
    return result


# ---------------------------------------------------------------------
#  Phase 10.2f — Profile + analytics
# ---------------------------------------------------------------------
#
# `/profile` returns the extended projection (incl. logo/website/etc).
# `/analytics` returns the Settings → Organization overview tiles
# counts. Both gate on `organization.manage` like every other org-level
# route in this module.


@router.get("/{org_id}/profile", response_model=OrganizationProfileRead)
async def get_profile(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationProfileRead:
    _ensure_active_tenant(tenant, org_id)
    return await service.get_org_profile(session, org_id=org_id)


@router.patch("/{org_id}/profile", response_model=OrganizationProfileRead)
async def update_profile(
    org_id: uuid.UUID,
    payload: OrganizationProfileUpdate,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationProfileRead:
    _ensure_active_tenant(tenant, org_id)
    result = await service.update_org_profile(
        session,
        actor_user_id=tenant.user_uuid,
        org_id=org_id,
        payload=payload,
    )
    await session.commit()
    return result


@router.get("/{org_id}/analytics", response_model=OrganizationAnalytics)
async def get_analytics(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationAnalytics:
    _ensure_active_tenant(tenant, org_id)
    return await service.get_org_analytics(session, org_id=org_id)


@router.delete("/{org_id}", response_model=OrganizationResponse)
async def archive_one(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    _ensure_active_tenant(tenant, org_id)
    result = await service.archive_org(
        session, actor_user_id=tenant.user_uuid, org_id=org_id
    )
    await session.commit()
    return result


# ---------------------------------------------------------------------
#  Danger zone — reset & purge (OWNER ONLY)
# ---------------------------------------------------------------------
#
# Both gate on `organization.manage` (resolves the tenant) AND an
# explicit owner check — admins can manage the org but only an owner may
# wipe or delete it.


@router.post("/{org_id}/reset", response_model=OrganizationResetResult)
async def reset_one(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> OrganizationResetResult:
    """Clear all user-provided content; keep the workspace shell."""
    _ensure_active_tenant(tenant, org_id)
    await _require_owner(session, tenant)
    result = await service.reset_organization_data(
        session, actor_user_id=tenant.user_uuid, org_id=org_id
    )
    await session.commit()
    return result


@router.post("/{org_id}/purge")
async def purge_one(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("organization.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """HARD delete the org and everything in it. Irreversible."""
    _ensure_active_tenant(tenant, org_id)
    await _require_owner(session, tenant)
    await service.purge_organization(
        session, actor_user_id=tenant.user_uuid, org_id=org_id
    )
    await session.commit()
    return {"status": "purged"}


# ---------------------------------------------------------------------
#  Members
# ---------------------------------------------------------------------


@router.get("/{org_id}/members", response_model=MemberList)
async def list_org_members(
    org_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> MemberList:
    _ensure_active_tenant(tenant, org_id)
    items = await service.list_members(session, org_id=org_id)
    return MemberList(items=items)


@router.put("/{org_id}/members/{member_id}/roles")
async def replace_member_roles(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberRoleUpdate,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    _ensure_active_tenant(tenant, org_id)
    roles = await service.replace_roles(
        session,
        actor_user_id=tenant.user_uuid,
        actor_member_id=tenant.member_id,
        org_id=org_id,
        member_id=member_id,
        role_slugs=payload.role_slugs,
    )
    await session.commit()
    return {"role_slugs": roles}


@router.post("/{org_id}/members/{member_id}/roles")
async def assign_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberAssignRole,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    _ensure_active_tenant(tenant, org_id)
    roles = await service.assign_role(
        session,
        actor_user_id=tenant.user_uuid,
        actor_member_id=tenant.member_id,
        org_id=org_id,
        member_id=member_id,
        role_slug=payload.role_slug,
    )
    await session.commit()
    return {"role_slugs": roles}


@router.delete("/{org_id}/members/{member_id}/roles/{role_slug}")
async def remove_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role_slug: str,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    _ensure_active_tenant(tenant, org_id)
    roles = await service.remove_role(
        session,
        actor_user_id=tenant.user_uuid,
        actor_member_id=tenant.member_id,
        org_id=org_id,
        member_id=member_id,
        role_slug=role_slug,
    )
    await session.commit()
    return {"role_slugs": roles}


@router.delete("/{org_id}/members/{member_id}")
async def remove_org_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _ensure_active_tenant(tenant, org_id)
    await service.remove_member(
        session,
        actor_user_id=tenant.user_uuid,
        actor_member_id=tenant.member_id,
        org_id=org_id,
        member_id=member_id,
    )
    await session.commit()
    return {"status": "removed"}


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _ensure_active_tenant(tenant: TenantContext, requested_org_id: uuid.UUID) -> None:
    """Belt-and-suspenders: TenantContext was resolved from X-Org-Id; if
    the URL path uses a different org_id, refuse — defends against
    'use my admin context against a different org' attacks."""
    if tenant.organization_id != requested_org_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant context does not match URL organization",
        )


async def _require_owner(session: AsyncSession, tenant: TenantContext) -> None:
    """Gate destructive ops (reset/purge) to the org owner. `require_permission`
    already proved `organization.manage`; this adds the owner-only floor."""
    if not await service.member_is_owner(session, tenant.member_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an organization owner can reset or delete the workspace",
        )
