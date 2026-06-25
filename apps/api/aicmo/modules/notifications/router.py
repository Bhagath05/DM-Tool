"""Phase 10.2b — HTTP surface for notification preferences.

Three endpoints. All authenticated. No extra permission slug: this is
self-service settings — every user controls their own toggles
regardless of role. Org-level + admin-overridable preferences land
later via the `source='admin'` row path; the schema already supports
it.

Endpoints:

  GET /api/v1/notifications/catalog
      Static descriptors. No tenant needed in principle, but we gate on
      require_tenant so the frontend can lazy-load it after sign-in
      without an unauthenticated bootstrap request. (Open to relaxing
      later if a public marketing page needs it.)

  GET /api/v1/notifications/preferences
      Materialised matrix for the authenticated (user, org).

  PUT /api/v1/notifications/preferences
      Bulk update. Returns the resulting matrix so the frontend can
      atomically replace its local cache without a second fetch.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.notifications import service
from aicmo.modules.notifications.schemas import (
    NotificationCatalog,
    PreferenceMatrix,
    UpdatePreferencesPayload,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_tenant


router = APIRouter(prefix="/notifications", tags=["notifications"])

# brand_optional=True — notification prefs are per-user-per-org. Brand
# context isn't needed (alerts span all brands in an org).
_RequireTenant = require_tenant(brand_optional=True)


@router.get(
    "/catalog",
    response_model=NotificationCatalog,
    status_code=status.HTTP_200_OK,
    summary="Static catalog of notification categories + channels",
)
async def get_catalog(
    _tenant: TenantContext = Depends(_RequireTenant),
) -> NotificationCatalog:
    """Return the category/channel descriptors. Same response for every
    user — frontend caches aggressively."""
    return service.get_catalog()


@router.get(
    "/preferences",
    response_model=PreferenceMatrix,
    status_code=status.HTTP_200_OK,
    summary="Current user's notification preference matrix for the active org",
)
async def get_preferences(
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> PreferenceMatrix:
    return await service.get_matrix(
        session,
        user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
    )


@router.put(
    "/preferences",
    response_model=PreferenceMatrix,
    status_code=status.HTTP_200_OK,
    summary="Bulk-update notification preferences",
)
async def update_preferences(
    payload: UpdatePreferencesPayload,
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> PreferenceMatrix:
    """Apply updates and return the resulting matrix.

    Locked cells (billing/security email) are silently coerced to
    enabled=True — see service module docstring.
    """
    return await service.upsert_preferences(
        session,
        user_id=tenant.user_uuid,
        organization_id=tenant.organization_id,
        updates=payload.updates,
    )
