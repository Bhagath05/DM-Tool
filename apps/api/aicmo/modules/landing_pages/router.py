from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.landing_pages import service
from aicmo.modules.landing_pages.schemas import (
    LandingPageCreate,
    LandingPageList,
    LandingPageResponse,
    LandingPageUpdate,
    PublicLandingPage,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

# ---------- auth'd customer surfaces ----------

router = APIRouter(prefix="/landing-pages", tags=["landing-pages"])


@router.post(
    "",
    response_model=LandingPageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_landing_page(
    payload: LandingPageCreate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.create")),
) -> LandingPageResponse:
    profile = await onboarding_service.require_profile(session, tenant.brand_id)
    return await service.create_page(
        session,
        tenant=tenant,
        business_profile_id=profile.id,
        payload=payload,
    )


@router.get("", response_model=LandingPageList)
async def list_landing_pages(
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> LandingPageList:
    items = await service.list_pages(
        session, tenant=tenant, include_archived=include_archived
    )
    return LandingPageList(items=items)


@router.get("/{page_id}", response_model=LandingPageResponse)
async def get_landing_page(
    page_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> LandingPageResponse:
    return await service.get_page(session, tenant=tenant, page_id=page_id)


@router.patch("/{page_id}", response_model=LandingPageResponse)
async def update_landing_page(
    page_id: uuid.UUID,
    payload: LandingPageUpdate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.edit")),
) -> LandingPageResponse:
    return await service.update_page(
        session, tenant=tenant, page_id=page_id, payload=payload
    )


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_landing_page(
    page_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("content.delete")),
) -> None:
    await service.delete_page(session, tenant=tenant, page_id=page_id)


# ---------- public surfaces (no auth) ----------

public_router = APIRouter(prefix="/public/landing-pages", tags=["public"])


@public_router.get("/{slug}", response_model=PublicLandingPage)
async def get_public_landing_page(
    slug: str,
    preview: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> PublicLandingPage:
    return await service.get_public(session, slug=slug, preview_token=preview)


@public_router.post(
    "/{slug}/view",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def record_landing_page_view(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    await service.record_view(session, slug=slug)
