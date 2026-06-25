"""Bundle API. Post W1-12: brand-scoped + permission-gated."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.bundles import service
from aicmo.modules.bundles.schemas import (
    BundleList,
    BundleResponse,
    GenerateBundleRequest,
)
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/bundles", tags=["bundles"])


@router.post(
    "/generate",
    response_model=BundleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_bundle(
    payload: GenerateBundleRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("campaign.create")),
) -> BundleResponse:
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before building a bundle",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)

    suggested_lp: uuid.UUID | None = None
    try:
        ctx = await build_generation_context(
            session, profile=profile, brand_id=tenant.brand_id
        )
        suggested_lp = ctx.preferences.suggested_landing_page_id
    except Exception:  # noqa: BLE001
        suggested_lp = None

    return await service.generate_bundle(
        session,
        tenant=tenant,
        profile=profile,
        payload=payload,
        suggested_landing_page_id=suggested_lp,
    )


@router.get("", response_model=BundleList)
async def list_bundles(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> BundleList:
    items = await service.list_bundles(session, tenant=tenant, limit=limit)
    return BundleList(items=items)


@router.get("/{bundle_id}", response_model=BundleResponse)
async def get_bundle(
    bundle_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> BundleResponse:
    return await service.get_bundle(
        session, tenant=tenant, bundle_id=bundle_id
    )
