"""Brands HTTP surface.

Two route trees:

    /api/v1/orgs/{org_id}/brands  →  list + create (org-scoped collection)
    /api/v1/brands/{brand_id}     →  get + update + archive (brand-scoped item)

Both require_permission("brand.manage") with brand_optional=True since
brand routes operate on the org itself, not a specific active brand.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.brands import service
from aicmo.modules.brands.schemas import (
    BrandActivateResult,
    BrandCreate,
    BrandList,
    BrandProfileRead,
    BrandProfileUpdate,
    BrandResponse,
    BrandSetDefaultResult,
    BrandUpdate,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

# Tree 1: /orgs/{org_id}/brands
org_router = APIRouter(prefix="/orgs", tags=["brands"])


@org_router.get("/{org_id}/brands", response_model=BrandList)
async def list_in_org(
    org_id: uuid.UUID,
    include_archived: bool = False,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> BrandList:
    _ensure_org_match(tenant, org_id)
    items = await service.list_brands(
        session,
        organization_id=org_id,
        include_archived=include_archived,
    )
    return BrandList(items=items)


@org_router.post(
    "/{org_id}/brands",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_in_org(
    org_id: uuid.UUID,
    payload: BrandCreate,
    tenant: TenantContext = Depends(
        require_permission("brand.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> BrandResponse:
    _ensure_org_match(tenant, org_id)
    result = await service.create_brand(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=org_id,
        payload=payload,
    )
    await session.commit()
    return result


# Tree 2: /brands/{brand_id}
brand_router = APIRouter(prefix="/brands", tags=["brands"])


@brand_router.get("/{brand_id}", response_model=BrandResponse)
async def get_one(
    brand_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> BrandResponse:
    return await service.get_brand(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
    )


@brand_router.patch("/{brand_id}", response_model=BrandResponse)
async def update_one(
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    tenant: TenantContext = Depends(
        require_permission("brand.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> BrandResponse:
    result = await service.update_brand(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        payload=payload,
    )
    await session.commit()
    return result


@brand_router.delete("/{brand_id}", response_model=BrandResponse)
async def archive_one(
    brand_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("brand.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> BrandResponse:
    result = await service.archive_brand(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
    )
    await session.commit()
    return result


# ---------------------------------------------------------------------
#  Phase 10.2f — Profile + default + activate
# ---------------------------------------------------------------------
#
# GET    /brands/{id}/profile    — extended projection
# PATCH  /brands/{id}/profile    — update name/desc/logo/website
# POST   /brands/{id}/default    — promote to org default
# POST   /brands/{id}/activate   — sticky last-active for the caller
#
# All four sit under `/brands/{brand_id}` and resolve the org from the
# tenant context (no `_ensure_org_match` needed — the service layer
# rejects cross-org IDs with a 404).


@brand_router.get("/{brand_id}/profile", response_model=BrandProfileRead)
async def get_profile(
    brand_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> BrandProfileRead:
    return await service.get_brand_profile(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
    )


@brand_router.patch("/{brand_id}/profile", response_model=BrandProfileRead)
async def update_profile(
    brand_id: uuid.UUID,
    payload: BrandProfileUpdate,
    tenant: TenantContext = Depends(
        require_permission("brand.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> BrandProfileRead:
    result = await service.update_brand_profile(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        payload=payload,
    )
    await session.commit()
    return result


@brand_router.post(
    "/{brand_id}/default",
    response_model=BrandSetDefaultResult,
)
async def set_default(
    brand_id: uuid.UUID,
    tenant: TenantContext = Depends(
        require_permission("brand.manage", brand_optional=True)
    ),
    session: AsyncSession = Depends(get_db),
) -> BrandSetDefaultResult:
    """Promote this brand to the org-wide default. Atomically clears
    any prior default. Idempotent if already default."""
    result = await service.set_default_brand(
        session,
        actor_user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
    )
    await session.commit()
    return result


@brand_router.post(
    "/{brand_id}/activate",
    response_model=BrandActivateResult,
)
async def activate(
    brand_id: uuid.UUID,
    tenant: TenantContext = Depends(require_tenant(brand_optional=True)),
    session: AsyncSession = Depends(get_db),
) -> BrandActivateResult:
    """Persist this brand as the caller's sticky last-active selection.

    No permission check beyond `require_tenant` — every member can pick
    which brand THEY land on; setting the org-wide default is a
    different operation gated on `brand.manage`.
    """
    result = await service.activate_brand_for_member(
        session,
        actor_user_id=tenant.user_uuid,
        actor_member_id=tenant.member_id,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
    )
    await session.commit()
    return result


def _ensure_org_match(tenant: TenantContext, requested_org_id: uuid.UUID) -> None:
    if tenant.organization_id != requested_org_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant context does not match URL organization",
        )
