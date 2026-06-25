"""Load connected platform metrics for intelligence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.connectors_models import ConnectorMetric
from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.integrations.models import IntegrationConnection


_METRIC_LABELS: dict[str, str] = {
    "reach_28d": "Reach (28 days)",
    "impressions_28d": "Impressions (28 days)",
    "engagement_rate": "Engagement rate",
    "followers": "Followers",
    "profile_views": "Profile views",
    "leads": "Leads",
    "call_clicks": "Phone calls",
    "website_clicks": "Website clicks",
    "direction_requests": "Direction requests",
    "reviews_count": "Reviews",
    "reviews_average_rating": "Average review rating",
    "accounts_engaged": "Accounts engaged",
}


async def load_connector_context(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> dict:
    """Real synced metrics only. Empty when no connectors or no sync data."""
    conn_stmt = (
        select(IntegrationConnection)
        .where(
            IntegrationConnection.brand_id == brand_id,
            IntegrationConnection.state == "ACTIVE",
        )
    )
    connections = (await session.execute(conn_stmt)).scalars().all()
    connected_providers = [c.provider_slug for c in connections]

    # Instagram uses the social module — reflect OAuth or manual-import syncs.
    from aicmo.modules.social.models import SocialConnection

    social_rows = (
        await session.execute(
            select(SocialConnection.platform).where(
                SocialConnection.brand_id == brand_id,
                SocialConnection.last_synced_at.isnot(None),
            )
        )
    ).scalars().all()
    for platform in social_rows:
        slug = f"{platform}_organic"
        if slug not in connected_providers:
            connected_providers.append(slug)

    cutoff = datetime.now(UTC) - timedelta(days=30)
    metrics_stmt = (
        select(ConnectorMetric)
        .where(
            ConnectorMetric.brand_id == brand_id,
            ConnectorMetric.synced_at >= cutoff,
        )
        .order_by(desc(ConnectorMetric.synced_at))
        .limit(50)
    )
    metric_rows = (await session.execute(metrics_stmt)).scalars().all()

    metrics = []
    data_sources: list[DataSourceRef] = []
    for m in metric_rows:
        label = _METRIC_LABELS.get(m.metric_key, m.metric_key.replace("_", " ").title())
        metrics.append(
            {
                "provider": m.provider_slug,
                "key": m.metric_key,
                "value": float(m.metric_value),
                "synced_at": m.synced_at.isoformat(),
            }
        )
        data_sources.append(
            DataSourceRef(
                key=f"{m.provider_slug}:{m.metric_key}",
                label=f"{m.provider_slug} — {label}",
                value=_format_metric_value(m.metric_key, float(m.metric_value)),
            )
        )

    last_sync = None
    if connections:
        sync_times = [c.last_sync_at for c in connections if c.last_sync_at]
        if sync_times:
            last_sync = max(sync_times).isoformat()

    return {
        "connected_providers": connected_providers,
        "metrics": metrics,
        "data_sources": data_sources,
        "last_sync_at": last_sync,
        "has_data": len(metrics) > 0,
    }


def _format_metric_value(key: str, value: float) -> str:
    if "rate" in key:
        return f"{value:.1%}" if value <= 1 else f"{value:.1f}%"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


async def upsert_metric(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    provider_slug: str,
    metric_key: str,
    metric_value: float,
    period_end: datetime | None = None,
    raw_json: dict | None = None,
) -> ConnectorMetric:
    """Upsert a synced metric row (called by provider sync)."""
    now = datetime.now(UTC)
    period_end = period_end or now

    existing = (
        await session.execute(
            select(ConnectorMetric).where(
                ConnectorMetric.brand_id == brand_id,
                ConnectorMetric.provider_slug == provider_slug,
                ConnectorMetric.metric_key == metric_key,
                ConnectorMetric.period_end == period_end,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.metric_value = metric_value
        existing.synced_at = now
        existing.raw_json = raw_json or {}
        return existing

    row = ConnectorMetric(
        id=uuid.uuid4(),
        brand_id=brand_id,
        provider_slug=provider_slug,
        metric_key=metric_key,
        metric_value=metric_value,
        period_end=period_end,
        raw_json=raw_json or {},
        synced_at=now,
    )
    session.add(row)
    return row
