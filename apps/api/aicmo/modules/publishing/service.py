"""Publishing service — schedule, publish, calendar, performance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor import service as advisor_service
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.publishing import assets as asset_registry
from aicmo.modules.publishing.connections import require_platform_connection
from aicmo.modules.publishing.models import ContentAsset, PublishEvent, ScheduledPost
from aicmo.modules.publishing.performance import (
    build_asset_performance,
    snapshot_recommendation_performance,
)
from aicmo.modules.publishing.publishers import (
    publish_facebook,
    publish_google_business_profile,
    publish_instagram,
    publish_linkedin,
    publish_pinterest,
    publish_youtube,
)
from aicmo.modules.publishing.schemas import (
    AssetPerformanceResponse,
    PublishEventList,
    PublishEventResponse,
    ScheduledPostList,
    ScheduledPostResponse,
    ScheduleFromRecommendationRequest,
    SchedulePostRequest,
)
from aicmo.modules.social.models import SocialAsset
from aicmo.tenancy.context import TenantContext

MAX_PUBLISH_ATTEMPTS = 3

log = structlog.get_logger()


async def schedule_post(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: SchedulePostRequest,
) -> ScheduledPostResponse:
    asset = await asset_registry.get_asset(
        session, brand_id=tenant.brand_id, asset_id=payload.content_asset_id
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    await require_platform_connection(
        session, brand_id=tenant.brand_id, platform=payload.platform
    )

    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)

    row = ScheduledPost(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        content_asset_id=asset.id,
        recommendation_id=asset.recommendation_id,
        platform=payload.platform,
        scheduled_at=scheduled_at,
        publish_status="scheduled",
    )
    session.add(row)
    asset.status = "scheduled"
    await _log_event(session, scheduled_post_id=row.id, event_type="scheduled", detail={})
    await session.commit()
    await session.refresh(row)

    if scheduled_at <= datetime.now(UTC):
        await publish_scheduled_post(session, scheduled_post_id=row.id, tenant=tenant)
        await session.refresh(row)

    return ScheduledPostResponse.model_validate(row)


async def schedule_from_recommendation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: ScheduleFromRecommendationRequest,
) -> ScheduledPostResponse:
    rec = await advisor_service.get_recommendation(
        session,
        brand_id=tenant.brand_id,
        recommendation_id=payload.recommendation_id,
    )
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        )
    if not rec.linked_asset_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generate an asset from this recommendation before scheduling.",
        )

    asset = (
        await session.execute(
            select(ContentAsset).where(
                ContentAsset.brand_id == tenant.brand_id,
                ContentAsset.source_id == rec.linked_asset_id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        if rec.linked_asset_type == "content":
            content = await session.get(GeneratedContent, rec.linked_asset_id)
            if content is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Linked asset not found"
                )
            asset = await asset_registry.register_from_content(
                session,
                tenant=tenant,
                content_id=content.id,
                content_type=content.content_type,
                platform=content.platform,
                output=content.output or {},
                recommendation_id=rec.id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Linked asset is not registered for publishing yet.",
            )

    return await schedule_post(
        session,
        tenant=tenant,
        payload=SchedulePostRequest(
            content_asset_id=asset.id,
            platform=payload.platform,
            scheduled_at=payload.scheduled_at,
        ),
    )


async def list_scheduled(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 50,
) -> ScheduledPostList:
    rows = (
        await session.execute(
            select(ScheduledPost)
            .where(ScheduledPost.brand_id == brand_id)
            .order_by(desc(ScheduledPost.scheduled_at))
            .limit(min(max(limit, 1), 100))
        )
    ).scalars().all()
    return ScheduledPostList(
        items=[ScheduledPostResponse.model_validate(r) for r in rows]
    )


async def _require_owned_post(
    session: AsyncSession, *, brand_id: uuid.UUID, scheduled_post_id: uuid.UUID
) -> ScheduledPost:
    """Load a scheduled post, enforcing tenant isolation. 404 if it doesn't
    exist OR belongs to another brand (never leak existence across tenants)."""
    row = await session.get(ScheduledPost, scheduled_post_id)
    if row is None or row.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled post not found"
        )
    return row


async def list_events(
    session: AsyncSession, *, brand_id: uuid.UUID, scheduled_post_id: uuid.UUID
) -> PublishEventList:
    """Audit trail for a scheduled post, chronological. Tenant-scoped via the
    owning post (PublishEvent has no brand_id of its own)."""
    await _require_owned_post(
        session, brand_id=brand_id, scheduled_post_id=scheduled_post_id
    )
    rows = (
        await session.execute(
            select(PublishEvent)
            .where(PublishEvent.scheduled_post_id == scheduled_post_id)
            .order_by(PublishEvent.created_at)
        )
    ).scalars().all()
    return PublishEventList(
        items=[PublishEventResponse.model_validate(r) for r in rows]
    )


async def retry_post(
    session: AsyncSession,
    *,
    scheduled_post_id: uuid.UUID,
    tenant: TenantContext,
) -> ScheduledPostResponse:
    """Operator-initiated retry of a failed/scheduled post. Resets the attempt
    budget (an explicit human decision) and re-runs the publish immediately."""
    row = await _require_owned_post(
        session, brand_id=tenant.brand_id, scheduled_post_id=scheduled_post_id
    )
    if row.publish_status == "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This post is already published.",
        )
    row.attempt_count = 0
    row.error_message = None
    row.publish_status = "scheduled"
    await _log_event(
        session, scheduled_post_id=row.id, event_type="retry_requested", detail={}
    )
    await session.flush()
    return await publish_scheduled_post(
        session, scheduled_post_id=row.id, tenant=tenant
    )


async def publish_scheduled_post(
    session: AsyncSession,
    *,
    scheduled_post_id: uuid.UUID,
    tenant: TenantContext | None = None,
) -> ScheduledPostResponse:
    row = await session.get(ScheduledPost, scheduled_post_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if row.publish_status == "published":
        return ScheduledPostResponse.model_validate(row)

    if row.attempt_count >= MAX_PUBLISH_ATTEMPTS:
        row.publish_status = "failed"
        row.error_message = row.error_message or "Max publish attempts reached."
        await session.commit()
        return ScheduledPostResponse.model_validate(row)

    asset = await session.get(ContentAsset, row.content_asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    conn = await require_platform_connection(
        session, brand_id=row.brand_id, platform=row.platform  # type: ignore[arg-type]
    )

    row.attempt_count += 1
    await _log_event(
        session,
        scheduled_post_id=row.id,
        event_type="publish_attempt",
        detail={"attempt": row.attempt_count},
    )

    try:
        if row.platform == "instagram":
            result = await publish_instagram(
                session,
                access_token=conn["access_token"],
                metadata=conn.get("metadata") or {},
                payload=asset.payload or {},
            )
        elif row.platform == "google_business_profile":
            result = await publish_google_business_profile(
                session,
                connection_id=conn["connection_id"],
                location_name=conn.get("external_account_id"),
                payload=asset.payload or {},
            )
        elif row.platform == "facebook":
            result = await publish_facebook(
                session,
                access_token=conn["access_token"],
                page_id=conn.get("external_account_id"),
                payload=asset.payload or {},
            )
        elif row.platform == "linkedin":
            result = await publish_linkedin(
                session,
                access_token=conn["access_token"],
                organization_id=conn.get("external_account_id"),
                payload=asset.payload or {},
            )
        elif row.platform == "youtube":
            result = await publish_youtube(
                session,
                access_token=conn["access_token"],
                channel_id=conn.get("external_account_id"),
                payload=asset.payload or {},
            )
        elif row.platform == "pinterest":
            result = await publish_pinterest(
                session,
                access_token=conn["access_token"],
                board_id=conn.get("external_account_id"),
                payload=asset.payload or {},
            )
        else:
            raise RuntimeError(f"Unsupported platform: {row.platform}")
    except Exception as exc:
        row.publish_status = "failed" if row.attempt_count >= MAX_PUBLISH_ATTEMPTS else "scheduled"
        row.error_message = str(exc)[:500]
        await _log_event(
            session,
            scheduled_post_id=row.id,
            event_type="failed",
            detail={"error": row.error_message},
        )
        asset.status = "failed"
        await session.commit()
        return ScheduledPostResponse.model_validate(row)

    now = datetime.now(UTC)
    row.publish_status = "published"
    row.platform_post_id = result.platform_post_id
    row.published_at = now
    row.error_message = None
    asset.status = "published"

    social_asset = None
    if conn.get("kind") == "social":
        social_asset = SocialAsset(
            id=uuid.uuid4(),
            user_id=row.user_id,
            organization_id=row.organization_id,
            brand_id=row.brand_id,
            connection_id=uuid.UUID(conn["connection_id"]),
            platform="instagram",
            platform_post_id=result.platform_post_id,
            asset_type=asset.asset_type,
            caption=(asset.payload or {}).get("output", {}).get("caption"),
            posted_at=now,
            raw_json={
                "source": "publishing_pipeline",
                "recommendation_id": str(row.recommendation_id)
                if row.recommendation_id
                else None,
                "publish_result": result.raw,
            },
        )
        session.add(social_asset)
        row.social_asset_id = social_asset.id

    await _log_event(
        session,
        scheduled_post_id=row.id,
        event_type="published",
        detail={
            "platform_post_id": result.platform_post_id,
            "recommendation_id": str(row.recommendation_id) if row.recommendation_id else None,
        },
    )
    await session.commit()
    await session.refresh(row)
    _ = tenant
    return ScheduledPostResponse.model_validate(row)


async def publish_due_posts(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int = 20,
) -> int:
    """Publish all due scheduled posts for a brand."""
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(ScheduledPost).where(
                ScheduledPost.brand_id == brand_id,
                ScheduledPost.publish_status == "scheduled",
                ScheduledPost.scheduled_at <= now,
                ScheduledPost.attempt_count < MAX_PUBLISH_ATTEMPTS,
            )
            .order_by(ScheduledPost.scheduled_at)
            .limit(limit)
        )
    ).scalars().all()
    count = 0
    for row in rows:
        await publish_scheduled_post(session, scheduled_post_id=row.id)
        count += 1
    return count


async def publish_all_due_posts(session: AsyncSession, *, limit: int = 100) -> int:
    """System-wide publish of every due scheduled post across ALL tenants.

    Used by the every-minute Arq cron (P0-3). Unlike `publish_due_posts` it
    has no brand filter. `publish_scheduled_post` commits per row, so a single
    failing post never blocks the rest — we roll back + skip + continue. The
    caller (cron) handles RLS bypass when RLS is enabled.
    """
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(ScheduledPost)
            .where(
                ScheduledPost.publish_status == "scheduled",
                ScheduledPost.scheduled_at <= now,
                ScheduledPost.attempt_count < MAX_PUBLISH_ATTEMPTS,
            )
            .order_by(ScheduledPost.scheduled_at)
            .limit(limit)
        )
    ).scalars().all()

    published = 0
    for row in rows:
        try:
            res = await publish_scheduled_post(session, scheduled_post_id=row.id)
            if res.publish_status == "published":
                published += 1
        except Exception as exc:
            await session.rollback()
            log.warning(
                "publish.cron.row_failed",
                scheduled_post_id=str(row.id),
                error=str(exc)[:200],
            )
    return published


async def get_asset_performance(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> AssetPerformanceResponse:
    asset = await asset_registry.get_asset(session, brand_id=brand_id, asset_id=asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    posts = (
        await session.execute(
            select(ScheduledPost)
            .where(ScheduledPost.content_asset_id == asset_id)
            .order_by(desc(ScheduledPost.scheduled_at))
        )
    ).scalars().all()

    metrics = await build_asset_performance(session, asset=asset, scheduled_posts=posts)
    return AssetPerformanceResponse(
        content_asset_id=asset.id,
        recommendation_id=asset.recommendation_id,
        metrics=metrics,
        scheduled_posts=[ScheduledPostResponse.model_validate(p) for p in posts],
    )


async def get_recommendation_performance(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    recommendation_id: uuid.UUID,
) -> dict:
    return await snapshot_recommendation_performance(
        session, brand_id=brand_id, recommendation_id=recommendation_id
    )


async def _log_event(
    session: AsyncSession,
    *,
    scheduled_post_id: uuid.UUID,
    event_type: str,
    detail: dict,
) -> None:
    session.add(
        PublishEvent(
            id=uuid.uuid4(),
            scheduled_post_id=scheduled_post_id,
            event_type=event_type,
            detail=detail,
        )
    )
