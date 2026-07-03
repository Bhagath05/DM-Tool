"""Phase 6.4 — enterprise publishing queue operations.

Extends the EXISTING publishing pipeline (service.py owns schedule + the
publish state machine + the every-minute cron) with the enterprise lifecycle
the base pipeline lacked: cancel / pause / resume / reschedule / bulk-schedule,
the approval gate (submit → approve / reject / request-changes), exponential
backoff timing, queue-level analytics, and notification emission.

Nothing here duplicates the base pipeline — cancel/pause/approval are new
states on the same `scheduled_posts` row, and the cron's due-query + failure
path (in service.py) are taught to honour them. All tenant-scoped + audited via
the reused PublishEvent log + the OperationsNotification feed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.publishing.models import PublishEvent, ScheduledPost
from aicmo.modules.publishing.schemas import (
    BulkScheduleRequest,
    PlatformHealth,
    QueueAnalyticsResponse,
    ScheduledPostResponse,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Exponential backoff between failed publish attempts (spec #9). attempt 1 →
# 5 min, 2 → 10 min, 3 → 20 min. Capped so a stuck row never waits absurdly long.
_BACKOFF_BASE_SECONDS = 300
_BACKOFF_CAP_SECONDS = 3600

# Statuses the cron will never auto-publish (approval gate + operator holds).
BLOCKED_APPROVALS = ("pending", "rejected", "changes_requested")
PUBLISHABLE_APPROVALS = ("not_required", "approved")


def backoff_seconds(attempt_count: int) -> int:
    """Seconds to wait before the next retry after `attempt_count` failures."""
    if attempt_count <= 0:
        return 0
    return min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** (attempt_count - 1)))


async def _owned(
    session: AsyncSession, *, brand_id: uuid.UUID, post_id: uuid.UUID
) -> ScheduledPost:
    row = await session.get(ScheduledPost, post_id)
    if row is None or row.brand_id != brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheduled post not found")
    return row


async def _event(session: AsyncSession, *, post_id: uuid.UUID, kind: str, detail: dict) -> None:
    session.add(
        PublishEvent(id=uuid.uuid4(), scheduled_post_id=post_id, event_type=kind, detail=detail)
    )


async def notify(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    kind: str,
    title: str,
    body: str,
    severity: str = "info",
    source_id: uuid.UUID | None = None,
) -> None:
    """Best-effort notification into the existing OperationsNotification feed
    (reuse — never a new feed). Publishing must never fail because a
    notification couldn't be staged."""
    try:
        from aicmo.modules.operations.models import OperationsNotification

        session.add(
            OperationsNotification(
                id=uuid.uuid4(),
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                category="publishing",
                kind=kind,
                severity=severity,
                title=title,
                body=body,
                source_id=source_id,
                dedupe_key=f"publishing:{kind}:{source_id}",
                read=False,
            )
        )
    except Exception as exc:
        log.warning("publishing.notify.skipped", kind=kind, error=str(exc)[:200])


# ---------------------------------------------------------------------
#  Lifecycle ops
# ---------------------------------------------------------------------
async def cancel_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID
) -> ScheduledPostResponse:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.publish_status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already published — cannot cancel.")
    row.publish_status = "cancelled"
    row.next_attempt_at = None
    await _event(session, post_id=row.id, kind="cancelled", detail={})
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def pause_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID
) -> ScheduledPostResponse:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.publish_status not in ("scheduled", "failed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot pause a {row.publish_status} post."
        )
    row.publish_status = "paused"
    await _event(session, post_id=row.id, kind="paused", detail={})
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def resume_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID
) -> ScheduledPostResponse:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.publish_status != "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, "Post is not paused.")
    row.publish_status = "scheduled"
    row.next_attempt_at = None
    await _event(session, post_id=row.id, kind="resumed", detail={})
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def reschedule_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID,
    scheduled_at: datetime, schedule_timezone: str | None = None,
) -> ScheduledPostResponse:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.publish_status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already published — cannot reschedule.")
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)
    row.scheduled_at = scheduled_at
    row.schedule_timezone = schedule_timezone
    row.publish_status = "scheduled"
    row.next_attempt_at = None
    row.error_message = None
    await _event(
        session, post_id=row.id, kind="rescheduled",
        detail={"scheduled_at": scheduled_at.isoformat(), "tz": schedule_timezone},
    )
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def bulk_schedule(
    session: AsyncSession, *, tenant: TenantContext, payload: BulkScheduleRequest,
) -> list[ScheduledPostResponse]:
    """Schedule many posts in one call. Reuses the base schedule path per item
    so ownership + connection checks still run; skips items whose asset/
    connection is missing rather than failing the whole batch."""
    from aicmo.modules.publishing import service
    from aicmo.modules.publishing.schemas import SchedulePostRequest

    out: list[ScheduledPostResponse] = []
    for item in payload.items:
        try:
            res = await service.schedule_post(
                session, tenant=tenant,
                payload=SchedulePostRequest(
                    content_asset_id=item.content_asset_id,
                    platform=item.platform,
                    scheduled_at=item.scheduled_at,
                ),
            )
        except HTTPException as exc:
            log.info("publishing.bulk.skipped", asset=str(item.content_asset_id), reason=exc.detail)
            continue
        # Apply the per-item enterprise fields the base schedule doesn't set.
        row = await session.get(ScheduledPost, res.id)
        if row is not None:
            row.schedule_timezone = item.schedule_timezone
            if item.approval_required:
                row.approval_required = True
                row.approval_status = "pending"
            await session.commit()
            await session.refresh(row)
            res = ScheduledPostResponse.model_validate(row)
        out.append(res)
    return out


# ---------------------------------------------------------------------
#  Approval gate
# ---------------------------------------------------------------------
async def submit_for_approval(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID
) -> ScheduledPostResponse:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.publish_status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already published.")
    row.approval_required = True
    row.approval_status = "pending"
    await _event(session, post_id=row.id, kind="approval_submitted", detail={})
    await notify(
        session, tenant=tenant, kind="approval_requested",
        title="Approval requested", body=f"A {row.platform} post needs your approval.",
        source_id=row.id,
    )
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def _decide(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID,
    decision: str, reason: str | None,
) -> ScheduledPost:
    row = await _owned(session, brand_id=tenant.brand_id, post_id=post_id)
    if row.approval_status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Post is not pending approval (status: {row.approval_status}).",
        )
    row.approval_status = decision
    row.reviewed_by_user_id = tenant.user_id
    row.approval_reason = reason
    await _event(
        session, post_id=row.id, kind=f"approval_{decision}",
        detail={"reason": reason, "by": tenant.user_id},
    )
    await notify(
        session, tenant=tenant, kind="approval_completed",
        title=f"Post {decision.replace('_', ' ')}",
        body=f"A {row.platform} post was {decision.replace('_', ' ')}.",
        severity="info" if decision == "approved" else "warning",
        source_id=row.id,
    )
    return row


async def approve_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID, reason: str | None,
) -> ScheduledPostResponse:
    row = await _decide(session, tenant=tenant, post_id=post_id, decision="approved", reason=reason)
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def reject_post(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID, reason: str | None,
) -> ScheduledPostResponse:
    row = await _decide(session, tenant=tenant, post_id=post_id, decision="rejected", reason=reason)
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


async def request_changes(
    session: AsyncSession, *, tenant: TenantContext, post_id: uuid.UUID, reason: str | None,
) -> ScheduledPostResponse:
    row = await _decide(
        session, tenant=tenant, post_id=post_id, decision="changes_requested", reason=reason
    )
    await session.commit()
    await session.refresh(row)
    return ScheduledPostResponse.model_validate(row)


# ---------------------------------------------------------------------
#  Queue analytics (spec #7)
# ---------------------------------------------------------------------
async def queue_analytics(
    session: AsyncSession, *, tenant: TenantContext
) -> QueueAnalyticsResponse:
    counts_stmt = (
        select(ScheduledPost.publish_status, func.count())
        .where(ScheduledPost.brand_id == tenant.brand_id)
        .group_by(ScheduledPost.publish_status)
    )
    by_status = {s: n for s, n in (await session.execute(counts_stmt)).all()}

    pending_stmt = select(func.count()).where(
        ScheduledPost.brand_id == tenant.brand_id,
        ScheduledPost.approval_status == "pending",
    )
    approval_pending = (await session.execute(pending_stmt)).scalar_one()

    retries_stmt = select(func.coalesce(func.sum(ScheduledPost.attempt_count), 0)).where(
        ScheduledPost.brand_id == tenant.brand_id
    )
    total_retries = int((await session.execute(retries_stmt)).scalar_one())

    published = by_status.get("published", 0)
    failed = by_status.get("failed", 0)
    scheduled = by_status.get("scheduled", 0)
    total_terminal = published + failed
    success_rate = round(published / total_terminal, 4) if total_terminal else 0.0

    # Average publish latency (schedule → published) over published rows.
    avg_stmt = select(
        func.avg(
            func.extract("epoch", ScheduledPost.published_at)
            - func.extract("epoch", ScheduledPost.scheduled_at)
        )
    ).where(
        ScheduledPost.brand_id == tenant.brand_id,
        ScheduledPost.publish_status == "published",
        ScheduledPost.published_at.isnot(None),
    )
    avg_secs = (await session.execute(avg_stmt)).scalar_one()
    avg_publish_seconds = round(float(avg_secs), 1) if avg_secs is not None else None

    # Per-platform health.
    plat_stmt = (
        select(ScheduledPost.platform, ScheduledPost.publish_status, func.count())
        .where(ScheduledPost.brand_id == tenant.brand_id)
        .group_by(ScheduledPost.platform, ScheduledPost.publish_status)
    )
    plat: dict[str, dict[str, int]] = {}
    for platform, st, n in (await session.execute(plat_stmt)).all():
        plat.setdefault(platform, {})[st] = n
    platform_health = []
    for platform, sts in sorted(plat.items()):
        pub = sts.get("published", 0)
        fail = sts.get("failed", 0)
        term = pub + fail
        platform_health.append(
            PlatformHealth(
                platform=platform, published=pub, failed=fail,
                scheduled=sts.get("scheduled", 0),
                success_rate=round(pub / term, 4) if term else 0.0,
            )
        )

    return QueueAnalyticsResponse(
        published=published, scheduled=scheduled,
        publishing=by_status.get("publishing", 0), failed=failed,
        cancelled=by_status.get("cancelled", 0), paused=by_status.get("paused", 0),
        approval_pending=approval_pending, draft=by_status.get("draft", 0),
        queue_length=scheduled + by_status.get("publishing", 0),
        total_retries=total_retries, success_rate=success_rate,
        avg_publish_seconds=avg_publish_seconds, platform_health=platform_health,
    )
