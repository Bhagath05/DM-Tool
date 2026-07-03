"""Link published post metrics back to recommendations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.leads.models import Lead
from aicmo.modules.publishing.models import ContentAsset, ScheduledPost
from aicmo.modules.publishing.schemas import PublishPerformanceMetrics
from aicmo.modules.social.models import PerformanceSignal


async def build_asset_performance(
    session: AsyncSession,
    *,
    asset: ContentAsset,
    scheduled_posts: list[ScheduledPost],
) -> PublishPerformanceMetrics | None:
    published = [p for p in scheduled_posts if p.publish_status == "published"]
    if not published:
        return None

    post = published[0]
    metrics = PublishPerformanceMetrics(
        recommendation_id=asset.recommendation_id,
        platform=post.platform,
        platform_post_id=post.platform_post_id,
    )

    if post.social_asset_id:
        signal = (
            await session.execute(
                select(PerformanceSignal)
                .where(PerformanceSignal.asset_id == post.social_asset_id)
                .order_by(desc(PerformanceSignal.captured_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if signal:
            metrics.reach = signal.reach or signal.impressions or 0
            metrics.impressions = signal.impressions or 0
            metrics.likes = signal.likes or 0
            metrics.comments = signal.comments_count or 0
            metrics.engagement = (
                signal.likes + signal.comments_count + signal.saves + signal.shares
            )

    if asset.recommendation_id and post.published_at:
        cutoff = post.published_at
        end = cutoff + timedelta(days=14)
        lead_count = (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.brand_id == asset.brand_id,
                    Lead.created_at >= cutoff,
                    Lead.created_at <= end,
                )
            )
        ).scalar_one()
        metrics.leads_in_window = int(lead_count or 0)

    return metrics


async def snapshot_recommendation_performance(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    recommendation_id: uuid.UUID,
) -> dict:
    """Aggregate publish + performance metrics for outcome learning."""
    assets = (
        await session.execute(
            select(ContentAsset).where(
                ContentAsset.brand_id == brand_id,
                ContentAsset.recommendation_id == recommendation_id,
            )
        )
    ).scalars().all()
    if not assets:
        return {}

    posts = (
        await session.execute(
            select(ScheduledPost).where(
                ScheduledPost.brand_id == brand_id,
                ScheduledPost.recommendation_id == recommendation_id,
                ScheduledPost.publish_status == "published",
            )
        )
    ).scalars().all()

    total_reach = 0
    total_engagement = 0
    total_leads = 0
    platforms: list[str] = []

    for post in posts:
        platforms.append(post.platform)
        if post.social_asset_id:
            signal = (
                await session.execute(
                    select(PerformanceSignal)
                    .where(PerformanceSignal.asset_id == post.social_asset_id)
                    .order_by(desc(PerformanceSignal.captured_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if signal:
                total_reach += signal.reach or signal.impressions or 0
                total_engagement += (
                    signal.likes + signal.comments_count + signal.saves + signal.shares
                )

        if post.published_at:
            end = post.published_at + timedelta(days=14)
            leads = (
                await session.execute(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        Lead.brand_id == brand_id,
                        Lead.created_at >= post.published_at,
                        Lead.created_at <= end,
                    )
                )
            ).scalar_one()
            total_leads += int(leads or 0)

    return {
        "published_count": len(posts),
        "platforms": platforms,
        "reach": total_reach,
        "engagement": total_engagement,
        "leads_in_window": total_leads,
        "snapshot_at": datetime.now(UTC).isoformat(),
    }
