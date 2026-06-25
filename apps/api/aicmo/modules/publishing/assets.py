"""Register generated sources into the unified content_assets registry."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.publishing.models import ContentAsset
from aicmo.tenancy.context import TenantContext

CONTENT_TYPE_TO_ASSET: dict[str, str] = {
    "social_post": "caption",
    "reel": "reel_script",
    "carousel": "carousel",
    "ad_copy": "ad_creative",
    "landing_page_copy": "caption",
}

VISUAL_TYPE_TO_ASSET: dict[str, str] = {
    "ad_creative": "ad_creative",
    "carousel": "carousel",
    "reel": "reel_script",
    "thumbnail": "poster",
}

AD_TYPE_TO_ASSET: dict[str, str] = {
    "meta": "ad_creative",
    "google_search": "ad_creative",
    "instagram_promo": "ad_creative",
    "linkedin": "ad_creative",
}


async def register_from_content(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    content_id: uuid.UUID,
    content_type: str,
    platform: str,
    output: dict,
    recommendation_id: uuid.UUID | None = None,
) -> ContentAsset:
    existing = (
        await session.execute(
            select(ContentAsset).where(
                ContentAsset.brand_id == tenant.brand_id,
                ContentAsset.source_table == "generated_content",
                ContentAsset.source_id == content_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if recommendation_id and not existing.recommendation_id:
            existing.recommendation_id = recommendation_id
        existing.payload = {
            **(existing.payload or {}),
            "content_type": content_type,
            "platform": platform,
            "output": output,
        }
        existing.status = "ready"
        return existing

    row = ContentAsset(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        recommendation_id=recommendation_id,
        asset_type=CONTENT_TYPE_TO_ASSET.get(content_type, "caption"),
        source_table="generated_content",
        source_id=content_id,
        status="ready",
        payload={
            "content_type": content_type,
            "platform": platform,
            "output": output,
        },
    )
    session.add(row)
    await session.flush()
    return row


async def register_from_ad(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    ad_id: uuid.UUID,
    ad_type: str,
    output: dict,
    recommendation_id: uuid.UUID | None = None,
) -> ContentAsset:
    row = ContentAsset(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        recommendation_id=recommendation_id,
        asset_type=AD_TYPE_TO_ASSET.get(ad_type, "ad_creative"),
        source_table="generated_ads",
        source_id=ad_id,
        status="ready",
        payload={"ad_type": ad_type, "output": output},
    )
    session.add(row)
    await session.flush()
    return row


async def register_from_visual(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    visual_id: uuid.UUID,
    visual_type: str,
    output: dict,
    recommendation_id: uuid.UUID | None = None,
) -> ContentAsset:
    row = ContentAsset(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        recommendation_id=recommendation_id,
        asset_type=VISUAL_TYPE_TO_ASSET.get(visual_type, "poster"),
        source_table="generated_visuals",
        source_id=visual_id,
        status="ready",
        payload={"visual_type": visual_type, "output": output},
    )
    session.add(row)
    await session.flush()
    return row


async def get_asset(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> ContentAsset | None:
    return (
        await session.execute(
            select(ContentAsset).where(
                ContentAsset.id == asset_id,
                ContentAsset.brand_id == brand_id,
            )
        )
    ).scalar_one_or_none()
