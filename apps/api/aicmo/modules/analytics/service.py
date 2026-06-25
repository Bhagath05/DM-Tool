"""Lead-acquisition analytics.

Pure SQL aggregates over the existing leads + landing_pages tables. No
AI calls, no per-row Python iteration — every endpoint is 1-2 round trips
to Postgres, sub-100ms even at 100k leads thanks to the indexes added in
0007_lead_capture.

Why no ORM joins / lazy loads: analytics queries are read-only aggregates;
we want explicit, inspectable SQL so the query planner picks the right
indexes. ORM relationship traversal hides this.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import cast, desc, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.analytics.schemas import (
    LandingPagePerformanceResponse,
    LandingPagePerformanceRow,
    OverviewKpis,
    SourceRow,
    SourcesResponse,
    StatusDistribution,
    TimelinePoint,
    TimelineResponse,
    TopAssetRow,
    TopAssetsResponse,
)
from aicmo.modules.campaigns.models import CampaignPlan
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.landing_pages.models import LandingPage
from aicmo.modules.leads.models import Lead
from aicmo.modules.visuals.models import GeneratedVisual


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- overview ----------


async def overview(session: AsyncSession, *, brand_id: uuid.UUID) -> OverviewKpis:
    now = _now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # One round-trip for all lead aggregates via FILTER clauses (Postgres
    # native, executed in a single scan).
    leads_stmt = select(
        func.count().label("total"),
        func.count().filter(Lead.created_at >= week_ago).label("w7"),
        func.count().filter(Lead.created_at >= month_ago).label("d30"),
        func.count().filter(Lead.status == "hot").label("hot"),
    ).where(Lead.brand_id == brand_id)
    leads_row = (await session.execute(leads_stmt)).one()

    # Pages aggregate — counters are denormalized so no JOIN needed.
    pages_stmt = select(
        func.count().filter(LandingPage.status == "published").label("published"),
        func.coalesce(func.sum(LandingPage.view_count), 0).label("views"),
        func.coalesce(func.sum(LandingPage.submission_count), 0).label("subs"),
    ).where(LandingPage.brand_id == brand_id, LandingPage.is_archived.is_(False))
    pages_row = (await session.execute(pages_stmt)).one()

    # Top page by submissions.
    top_stmt = (
        select(
            LandingPage.title,
            LandingPage.slug,
            LandingPage.submission_count,
        )
        .where(
            LandingPage.brand_id == brand_id,
            LandingPage.is_archived.is_(False),
        )
        .order_by(desc(LandingPage.submission_count))
        .limit(1)
    )
    top_row = (await session.execute(top_stmt)).first()

    views = int(pages_row.views)
    subs = int(pages_row.subs)
    conversion = (subs / views) if views > 0 else 0.0

    return OverviewKpis(
        total_leads=int(leads_row.total),
        leads_7d=int(leads_row.w7),
        leads_30d=int(leads_row.d30),
        hot_leads=int(leads_row.hot),
        landing_pages_published=int(pages_row.published),
        total_views=views,
        total_submissions=subs,
        conversion_rate=conversion,
        top_landing_page_title=top_row.title if top_row else None,
        top_landing_page_slug=top_row.slug if top_row else None,
        top_landing_page_submissions=int(top_row.submission_count) if top_row else 0,
    )


# ---------- timeline ----------


async def timeline(
    session: AsyncSession, *, brand_id: uuid.UUID, window_days: int
) -> TimelineResponse:
    window_days = max(1, min(window_days, 365))
    cutoff = _now() - timedelta(days=window_days)

    # date_trunc returns timestamps — cast to date for clean rendering.
    day_col = func.date_trunc("day", Lead.created_at).label("day")
    stmt = (
        select(day_col, func.count().label("c"))
        .where(Lead.brand_id == brand_id, Lead.created_at >= cutoff)
        .group_by(day_col)
        .order_by(day_col)
    )
    rows = (await session.execute(stmt)).all()

    # Backfill empty days so the chart has continuous bars.
    counts: dict[date, int] = {}
    for r in rows:
        d = r.day.date() if hasattr(r.day, "date") else r.day
        counts[d] = int(r.c)

    today = _now().date()
    start = today - timedelta(days=window_days - 1)
    points: list[TimelinePoint] = []
    for i in range(window_days):
        d = start + timedelta(days=i)
        points.append(TimelinePoint(day=d, leads=counts.get(d, 0)))

    total = sum(p.leads for p in points)
    return TimelineResponse(days=points, total=total, window_days=window_days)


# ---------- by source ----------


async def by_source(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int
) -> SourcesResponse:
    limit = max(1, min(limit, 100))
    hot_count = func.count().filter(Lead.status == "hot").label("hot")
    stmt = (
        select(
            Lead.source_asset_type,
            Lead.utm_source,
            Lead.utm_medium,
            Lead.utm_campaign,
            func.count().label("leads"),
            hot_count,
        )
        .where(Lead.brand_id == brand_id)
        .group_by(
            Lead.source_asset_type,
            Lead.utm_source,
            Lead.utm_medium,
            Lead.utm_campaign,
        )
        .order_by(desc("leads"))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        SourceRow(
            source_asset_type=r.source_asset_type,
            utm_source=r.utm_source,
            utm_medium=r.utm_medium,
            utm_campaign=r.utm_campaign,
            leads=int(r.leads),
            hot_leads=int(r.hot),
        )
        for r in rows
    ]
    return SourcesResponse(items=items)


# ---------- landing page performance ----------


async def landing_page_performance(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> LandingPagePerformanceResponse:
    # LEFT JOIN so pages with zero leads still appear (and conversion = 0).
    hot_count = func.count(Lead.id).filter(Lead.status == "hot").label("hot")
    stmt = (
        select(
            LandingPage.id,
            LandingPage.slug,
            LandingPage.title,
            LandingPage.status,
            LandingPage.view_count,
            LandingPage.submission_count,
            hot_count,
        )
        .outerjoin(Lead, Lead.landing_page_id == LandingPage.id)
        .where(
            LandingPage.brand_id == brand_id,
            LandingPage.is_archived.is_(False),
        )
        .group_by(LandingPage.id)
        .order_by(desc(LandingPage.submission_count))
    )
    rows = (await session.execute(stmt)).all()
    items = [
        LandingPagePerformanceRow(
            id=r.id,
            slug=r.slug,
            title=r.title,
            status=r.status,
            view_count=int(r.view_count),
            submission_count=int(r.submission_count),
            conversion_rate=(
                int(r.submission_count) / int(r.view_count)
                if r.view_count and r.view_count > 0
                else 0.0
            ),
            hot_leads=int(r.hot),
        )
        for r in rows
    ]
    return LandingPagePerformanceResponse(items=items)


# ---------- top-converting assets ----------


async def top_assets(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int
) -> TopAssetsResponse:
    """Per-asset lead counts joined to the source asset for label metadata.

    Polymorphic — 4 grouped queries (one per asset_type), merged + sorted in
    Python. At MVP scale (hundreds of assets per user) this is sub-50ms with
    the existing user_id indexes.

    Why per-type queries instead of UNION ALL: SQLAlchemy can build the
    statements composably with the right typed columns, and we get clean
    Pydantic models out without case-statement gymnastics. The merge step
    is O(rows) and trivial.
    """
    limit = max(1, min(limit, 50))

    leads_col = func.count(Lead.id).label("leads")
    hot_col = func.count(Lead.id).filter(Lead.status == "hot").label("hot")
    lead_id_as_uuid = cast(Lead.source_asset_id, PG_UUID(as_uuid=True))

    # ---- content ----
    content_stmt = (
        select(
            GeneratedContent.id,
            GeneratedContent.content_type,
            GeneratedContent.platform,
            GeneratedContent.goal,
            GeneratedContent.created_at,
            leads_col,
            hot_col,
        )
        .join(
            Lead,
            (Lead.brand_id == brand_id)
            & (Lead.source_asset_type == "content")
            & (lead_id_as_uuid == GeneratedContent.id),
        )
        .where(GeneratedContent.brand_id == brand_id)
        .group_by(GeneratedContent.id)
        .order_by(desc("leads"))
        .limit(limit)
    )

    # ---- ads ----
    ad_stmt = (
        select(
            GeneratedAd.id,
            GeneratedAd.ad_type,
            GeneratedAd.platform,
            GeneratedAd.goal,
            GeneratedAd.created_at,
            leads_col,
            hot_col,
        )
        .join(
            Lead,
            (Lead.brand_id == brand_id)
            & (Lead.source_asset_type == "ad")
            & (lead_id_as_uuid == GeneratedAd.id),
        )
        .where(GeneratedAd.brand_id == brand_id)
        .group_by(GeneratedAd.id)
        .order_by(desc("leads"))
        .limit(limit)
    )

    # ---- visuals ----
    visual_stmt = (
        select(
            GeneratedVisual.id,
            GeneratedVisual.visual_type,
            GeneratedVisual.platform,
            GeneratedVisual.goal,
            GeneratedVisual.created_at,
            leads_col,
            hot_col,
        )
        .join(
            Lead,
            (Lead.brand_id == brand_id)
            & (Lead.source_asset_type == "visual")
            & (lead_id_as_uuid == GeneratedVisual.id),
        )
        .where(GeneratedVisual.brand_id == brand_id)
        .group_by(GeneratedVisual.id)
        .order_by(desc("leads"))
        .limit(limit)
    )

    # ---- campaigns ----
    # No single platform column — leave it null in the response.
    campaign_stmt = (
        select(
            CampaignPlan.id,
            CampaignPlan.campaign_type,
            CampaignPlan.goal,
            CampaignPlan.created_at,
            leads_col,
            hot_col,
        )
        .join(
            Lead,
            (Lead.brand_id == brand_id)
            & (Lead.source_asset_type == "campaign")
            & (lead_id_as_uuid == CampaignPlan.id),
        )
        .where(CampaignPlan.brand_id == brand_id)
        .group_by(CampaignPlan.id)
        .order_by(desc("leads"))
        .limit(limit)
    )

    content_rows, ad_rows, visual_rows, campaign_rows = (
        (await session.execute(content_stmt)).all(),
        (await session.execute(ad_stmt)).all(),
        (await session.execute(visual_stmt)).all(),
        (await session.execute(campaign_stmt)).all(),
    )

    items: list[TopAssetRow] = []
    for r in content_rows:
        items.append(
            TopAssetRow(
                source_asset_type="content",
                source_asset_id=r.id,
                subtype=r.content_type,
                platform=r.platform,
                goal=r.goal,
                leads=int(r.leads),
                hot_leads=int(r.hot),
                created_at=r.created_at,
            )
        )
    for r in ad_rows:
        items.append(
            TopAssetRow(
                source_asset_type="ad",
                source_asset_id=r.id,
                subtype=r.ad_type,
                platform=r.platform,
                goal=r.goal,
                leads=int(r.leads),
                hot_leads=int(r.hot),
                created_at=r.created_at,
            )
        )
    for r in visual_rows:
        items.append(
            TopAssetRow(
                source_asset_type="visual",
                source_asset_id=r.id,
                subtype=r.visual_type,
                platform=r.platform,
                goal=r.goal,
                leads=int(r.leads),
                hot_leads=int(r.hot),
                created_at=r.created_at,
            )
        )
    for r in campaign_rows:
        items.append(
            TopAssetRow(
                source_asset_type="campaign",
                source_asset_id=r.id,
                subtype=r.campaign_type,
                platform=None,
                goal=r.goal,
                leads=int(r.leads),
                hot_leads=int(r.hot),
                created_at=r.created_at,
            )
        )

    # Global sort across all 4 types; ties broken by recency (newer first).
    items.sort(key=lambda x: (-x.leads, -x.created_at.timestamp()))
    return TopAssetsResponse(items=items[:limit])


# ---------- status distribution ----------


async def status_distribution(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> StatusDistribution:
    stmt = (
        select(Lead.status, func.count().label("c"))
        .where(Lead.brand_id == brand_id)
        .group_by(Lead.status)
    )
    rows = (await session.execute(stmt)).all()
    counts: dict[str, int] = {r.status: int(r.c) for r in rows}
    return StatusDistribution(
        new=counts.get("new", 0),
        hot=counts.get("hot", 0),
        warm=counts.get("warm", 0),
        cold=counts.get("cold", 0),
        archived=counts.get("archived", 0),
    )
