"""Context API surface. Post W1-12: brand-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/snapshot", response_model=GenerationContext)
async def get_snapshot(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> GenerationContext:
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before requesting context",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)
    return await build_generation_context(
        session, profile=profile, brand_id=tenant.brand_id
    )
