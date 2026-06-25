"""Check platform connections before scheduling or publishing."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.modules.integrations.service import ensure_access_token
from aicmo.modules.publishing.schemas import PublishPlatform
from aicmo.modules.social.models import SocialConnection
from aicmo.modules.social.token_crypto import unseal

# Maps publish platform → integration provider slug in the registry.
_INTEGRATION_SLUGS: dict[str, str] = {
    "facebook": "facebook_pages",
    "linkedin": "linkedin_organic",
    "youtube": "youtube",
    "pinterest": "pinterest",
    "google_business_profile": "google_business_profile",
}


async def require_platform_connection(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    platform: PublishPlatform,
) -> dict:
    """Return connection metadata needed for publish. Raises 409 if not connected."""
    if platform == "instagram":
        row = (
            await session.execute(
                select(SocialConnection).where(
                    SocialConnection.brand_id == brand_id,
                    SocialConnection.platform == "instagram",
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.access_token:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect Instagram before scheduling or publishing.",
            )
        return {
            "kind": "social",
            "connection_id": str(row.id),
            "access_token": unseal(row.access_token),
            "metadata": row.metadata_json or {},
        }

    provider_slug = _INTEGRATION_SLUGS.get(platform)
    if provider_slug:
        row = (
            await session.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.brand_id == brand_id,
                    IntegrationConnection.provider_slug == provider_slug,
                    IntegrationConnection.state == "ACTIVE",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Connect {platform.replace('_', ' ').title()} before scheduling or publishing.",
            )
        access_token = await ensure_access_token(session, row)
        return {
            "kind": "integration",
            "connection_id": str(row.id),
            "external_account_id": row.external_account_id,
            "access_token": access_token,
            "provider_slug": provider_slug,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported platform: {platform}",
    )
