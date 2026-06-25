"""RBAC HTTP surface.

Two route trees:

    /api/v1/rbac/permissions          → read-only catalogue
    /api/v1/orgs/{org_id}/roles/*     → CRUD on roles (org-scoped)
    /api/v1/orgs/{org_id}/members/{member_id}/permissions
                                      → resolved permission lookup

System roles are visible via the list but not modifiable. Custom roles
require `team.manage` to create / edit / delete.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.db.session import get_db
from aicmo.modules.orgs import service as orgs_service
from aicmo.modules.rbac import service
from aicmo.modules.rbac.schemas import (
    MemberPermissionsResponse,
    PermissionList,
    RoleCreate,
    RoleList,
    RoleResponse,
    RoleUpdate,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant
from aicmo.tenancy.permissions import (
    compute_permissions_for_member,
    compute_role_slugs_for_member,
)

# Tree 1: /rbac/permissions (catalogue — same for every org)
catalog_router = APIRouter(prefix="/rbac", tags=["rbac"])


@catalog_router.get("/permissions", response_model=PermissionList)
async def list_perms(
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> PermissionList:
    """Public to any authenticated user. Used by the permission editor UI."""
    items = await service.list_permissions(session)
    return PermissionList(items=items)


# Tree 2: /orgs/{org_id}/roles (org-scoped role management)
org_router = APIRouter(prefix="/orgs", tags=["rbac"])


@org_router.get("/{org_id}/roles", response_model=RoleList)
async def list_org_roles(
    org_id: uuid.UUID,
    include_system: bool = True,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> RoleList:
    _ensure_org_match(tenant, org_id)
    items = await service.list_roles(
        session,
        organization_id=org_id,
        include_system=include_system,
    )
    return RoleList(items=items)


@org_router.get("/{org_id}/roles/{role_id}", response_model=RoleResponse)
async def get_org_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> RoleResponse:
    _ensure_org_match(tenant, org_id)
    return await service.get_role(
        session, organization_id=org_id, role_id=role_id
    )


@org_router.post(
    "/{org_id}/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_role(
    org_id: uuid.UUID,
    payload: RoleCreate,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> RoleResponse:
    _ensure_org_match(tenant, org_id)
    result = await service.create_role(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=org_id,
        payload=payload,
    )
    await session.commit()
    return result


@org_router.patch(
    "/{org_id}/roles/{role_id}", response_model=RoleResponse
)
async def update_org_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: RoleUpdate,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> RoleResponse:
    _ensure_org_match(tenant, org_id)
    result = await service.update_role(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=org_id,
        role_id=role_id,
        payload=payload,
    )
    await session.commit()
    return result


@org_router.delete(
    "/{org_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_org_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    _ensure_org_match(tenant, org_id)
    await service.delete_role(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=org_id,
        role_id=role_id,
    )
    await session.commit()


@org_router.get(
    "/{org_id}/members/{member_id}/permissions",
    response_model=MemberPermissionsResponse,
)
async def member_permissions(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("team.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> MemberPermissionsResponse:
    """Resolved permission lookup. Useful for the role-editor UI ("what
    can this person actually do?") + for support debugging."""
    _ensure_org_match(tenant, org_id)
    # Confirm member belongs to this org
    await orgs_service.get_member(
        session, org_id=org_id, member_id=member_id
    )
    roles = await compute_role_slugs_for_member(session, member_id)
    perms = await compute_permissions_for_member(session, member_id)
    return MemberPermissionsResponse(
        member_id=member_id,
        role_slugs=sorted(roles),
        permission_slugs=sorted(perms),
    )


def _ensure_org_match(tenant: TenantContext, requested_org_id: uuid.UUID) -> None:
    if tenant.organization_id != requested_org_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant context does not match URL organization",
        )
