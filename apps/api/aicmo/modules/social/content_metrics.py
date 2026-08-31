"""Phase 5 — per-content metrics collection for integration providers.

Closes the loop for Facebook / YouTube / LinkedIn / Pinterest posts published
through the pipeline: it reads the published `ScheduledPost` rows (which carry
`platform_post_id`), asks each provider for that post's real metrics via the
existing OAuth credential flow, and writes them into the EXISTING per-content
store (`SocialAsset` + `PerformanceSignal`) — no new metrics table.

Guarantees (mirroring the Phase-2 account-level cron):
- **Idempotent + incremental:** `SocialAsset` is upserted on
  (brand, platform, platform_post_id); a post polled within the freshness
  window is skipped, so re-runs don't hammer provider APIs or duplicate assets.
- **Failure isolated:** each connection runs in its own session; one
  provider/account failure never aborts the run.
- **Rate-limit aware:** a bounded number of posts per connection per run.
- **Tenant scoped:** every query filters by the connection's `brand_id`.
- **Secret safe:** tokens are resolved via `ensure_access_token` (decrypt +
  refresh) and never logged — logs carry only provider slug + exception type.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import SessionLocal
from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.modules.integrations.providers.base import ContentMetricResult, ContentRef
from aicmo.modules.integrations.registry import IntegrationRegistry
from aicmo.modules.integrations.service import ensure_access_token
from aicmo.modules.publishing.models import ScheduledPost
from aicmo.modules.social.models import PerformanceSignal, SocialAsset

log = structlog.get_logger()

# provider registry slug → the publish `platform` string used on ScheduledPost
# and SocialAsset. Only providers that implement `fetch_content_metrics`.
_PROVIDER_PLATFORM: dict[str, str] = {
    "facebook_pages": "facebook",
    "youtube": "youtube",
    "linkedin_organic": "linkedin",
    "pinterest": "pinterest",
}

# Only measure recently-published posts; don't re-poll a post too often; cap the
# number of posts per connection per run so a large account can't stampede.
_LOOKBACK_DAYS = 60
_FRESH_AFTER = timedelta(hours=12)
_MAX_POSTS_PER_RUN = 50
_MAX_CONCURRENCY = 3


def _default_asset_type(platform: str) -> str:
    if platform == "youtube":
        return "video"
    if platform == "pinterest":
        return "image"
    return "post"


def _now() -> datetime:
    return datetime.now(UTC)


async def _due_published_posts(
    session: AsyncSession, *, brand_id: uuid.UUID, platform: str
) -> list[ScheduledPost]:
    cutoff = _now() - timedelta(days=_LOOKBACK_DAYS)
    stmt = (
        select(ScheduledPost)
        .where(
            ScheduledPost.brand_id == brand_id,
            ScheduledPost.platform == platform,
            ScheduledPost.publish_status == "published",
            ScheduledPost.platform_post_id.is_not(None),
            ScheduledPost.published_at.is_not(None),
            ScheduledPost.published_at >= cutoff,
        )
        .order_by(ScheduledPost.published_at.desc())
        .limit(200)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _existing_assets(
    session: AsyncSession, *, brand_id: uuid.UUID, platform: str, post_ids: list[str]
) -> dict[str, SocialAsset]:
    if not post_ids:
        return {}
    stmt = select(SocialAsset).where(
        SocialAsset.brand_id == brand_id,
        SocialAsset.platform == platform,
        SocialAsset.platform_post_id.in_(post_ids),
    )
    return {a.platform_post_id: a for a in (await session.execute(stmt)).scalars().all()}


def _engagement_rate(m: dict[str, float]) -> float:
    denom = max(m.get("impressions") or m.get("reach") or m.get("views") or 1, 1)
    engagement = (
        m.get("likes", 0) + m.get("comments_count", 0) + m.get("saves", 0) + m.get("shares", 0)
    )
    return round(engagement / denom, 4) if engagement else 0.0


def _write_asset_and_signal(
    session: AsyncSession,
    *,
    connection: IntegrationConnection,
    platform: str,
    scheduled_post: ScheduledPost,
    existing: SocialAsset | None,
    result: ContentMetricResult,
) -> None:
    """Upsert the SocialAsset (idempotent) + append one PerformanceSignal.

    Tenant identity (user_id/org/brand) comes from the ScheduledPost, which is
    the authoritative attribution row for the published post."""
    now = _now()
    if existing is None:
        asset = SocialAsset(
            id=uuid.uuid4(),
            user_id=scheduled_post.user_id,
            organization_id=scheduled_post.organization_id,
            brand_id=scheduled_post.brand_id,
            connection_id=None,  # integration provider — no social connection
            provider_slug=connection.provider_slug,
            integration_connection_id=connection.id,
            platform=platform,
            platform_post_id=result.platform_post_id,
            asset_type=result.asset_type,
            permalink=result.permalink,
            posted_at=result.posted_at or scheduled_post.published_at,
            raw_json={"source": "content_metrics_collection", **(result.raw or {})},
        )
        session.add(asset)
    else:
        asset = existing
        asset.provider_slug = connection.provider_slug
        asset.integration_connection_id = connection.id
        asset.asset_type = result.asset_type or asset.asset_type
        if result.permalink:
            asset.permalink = result.permalink
        asset.raw_json = {
            **(asset.raw_json or {}),
            "source": "content_metrics_collection",
            **(result.raw or {}),
        }

    m = result.metrics or {}
    session.add(
        PerformanceSignal(
            id=uuid.uuid4(),
            asset_id=asset.id,
            impressions=int(m.get("impressions", 0)),
            reach=int(m.get("reach", 0)),
            likes=int(m.get("likes", 0)),
            comments_count=int(m.get("comments_count", 0)),
            saves=int(m.get("saves", 0)),
            shares=int(m.get("shares", 0)),
            engagement_rate=_engagement_rate(m),
            views=int(m.get("views", 0)),
            watch_time_seconds=float(m.get("watch_time_seconds", 0.0)),
            ctr=float(m.get("ctr", 0.0)),
            # `metrics` records EXACTLY which keys the provider returned, so the
            # analytics layer can tell a real 0 from an unavailable metric.
            raw_json={"metrics": m},
            captured_at=now,
        )
    )


async def collect_for_connection(
    session: AsyncSession, *, connection: IntegrationConnection
) -> int:
    """Collect per-content metrics for one integration connection. Returns the
    number of posts written. Commits on success."""
    provider_slug = connection.provider_slug
    platform = _PROVIDER_PLATFORM.get(provider_slug)
    if platform is None or connection.brand_id is None:
        return 0
    provider = IntegrationRegistry.get(provider_slug)
    if not getattr(provider, "content_metrics_supported", False):
        return 0

    posts = await _due_published_posts(session, brand_id=connection.brand_id, platform=platform)
    if not posts:
        return 0

    # Dedupe by platform_post_id (keep the most recent ScheduledPost per id).
    sp_by_id: dict[str, ScheduledPost] = {}
    for sp in posts:
        pid = sp.platform_post_id
        if pid and pid not in sp_by_id:
            sp_by_id[pid] = sp

    existing = await _existing_assets(
        session, brand_id=connection.brand_id, platform=platform, post_ids=list(sp_by_id)
    )
    fresh_cutoff = _now() - _FRESH_AFTER
    refs: list[ContentRef] = []
    for pid in sp_by_id:
        a = existing.get(pid)
        if a is not None and a.updated_at and a.updated_at > fresh_cutoff:
            continue  # incremental: polled recently, skip
        refs.append(ContentRef(platform_post_id=pid, asset_type=_default_asset_type(platform)))
        if len(refs) >= _MAX_POSTS_PER_RUN:
            break
    if not refs:
        return 0

    token = await ensure_access_token(session, connection)  # decrypt+refresh; never logged
    results = await provider.fetch_content_metrics(
        access_token=token,
        external_account_id=connection.external_account_id,
        posts=refs,
    )

    written = 0
    for res in results:
        sp = sp_by_id.get(res.platform_post_id)
        if sp is None:
            continue
        _write_asset_and_signal(
            session,
            connection=connection,
            platform=platform,
            scheduled_post=sp,
            existing=existing.get(res.platform_post_id),
            result=res,
        )
        written += 1

    if written:
        await session.commit()
    return written


async def _due_connection_ids(session: AsyncSession) -> list[uuid.UUID]:
    stmt = select(IntegrationConnection.id).where(
        IntegrationConnection.state == "ACTIVE",
        IntegrationConnection.provider_slug.in_(list(_PROVIDER_PLATFORM)),
    )
    return list((await session.execute(stmt)).scalars().all())


async def _collect_one(connection_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        conn = await session.get(IntegrationConnection, connection_id)
        if conn is None or conn.state != "ACTIVE":
            return 0
        provider = conn.provider_slug
        try:
            return await collect_for_connection(session, connection=conn)
        except Exception as e:  # isolate — one account never aborts the run
            log.warning(
                "social.content_metrics.connection_failed",
                connection_id=str(connection_id),
                provider=provider,
                error_type=type(e).__name__,
            )
            return 0


async def collect_content_metrics_cron(ctx: dict) -> dict:
    """Scheduled per-content collection across all tenants/accounts. Idempotent
    and incremental; safe to run repeatedly."""
    async with SessionLocal() as session:
        due = await _due_connection_ids(session)
    if not due:
        log.info("social.content_metrics.done", due=0, collected=0)
        return {"due": 0, "collected": 0}

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _guarded(cid: uuid.UUID) -> int:
        async with sem:
            return await _collect_one(cid)

    results = await asyncio.gather(*[_guarded(cid) for cid in due])
    collected = sum(results)
    log.info("social.content_metrics.done", due=len(due), collected=collected)
    return {"due": len(due), "collected": collected}
