"""Lead Intelligence context for the advisor — hot, cold, lost, follow-ups."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.leads.models import Lead


async def load_lead_context(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> dict:
    """Aggregate lead buckets and follow-up priorities — real counts only."""
    counts_stmt = select(
        func.count().label("total"),
        func.count().filter(Lead.status == "hot").label("hot"),
        func.count().filter(Lead.status == "warm").label("warm"),
        func.count().filter(Lead.status == "cold").label("cold"),
        func.count().filter(Lead.status == "new").label("new"),
        func.count().filter(Lead.status == "archived").label("lost"),
    ).where(Lead.brand_id == brand_id)
    counts = (await session.execute(counts_stmt)).one()

    insights: list[str] = []
    data_sources: list[DataSourceRef] = []

    total = int(counts.total)
    hot = int(counts.hot)
    warm = int(counts.warm)
    cold = int(counts.cold)
    new = int(counts.new)
    lost = int(counts.lost)

    if total == 0:
        return {
            "insights": ["No leads in pipeline"],
            "data_sources": [],
            "has_data": False,
            "follow_up_priority": None,
            "counts": {},
        }

    insights.append(f"Pipeline: {hot} hot, {warm} warm, {cold} cold, {new} new, {lost} lost/archived")
    data_sources.append(DataSourceRef(key="hot_leads", label="Hot leads", value=str(hot)))
    data_sources.append(DataSourceRef(key="lost_leads", label="Lost/archived", value=str(lost)))

    week_ago = datetime.now(UTC) - timedelta(days=7)
    stale_hot = (
        await session.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.brand_id == brand_id,
                Lead.status == "hot",
                Lead.updated_at < week_ago,
            )
        )
    ).scalar_one()
    if stale_hot and stale_hot > 0:
        insights.append(
            f"{stale_hot} hot lead(s) with no activity in 7+ days — follow up urgently"
        )

    priority_stmt = (
        select(Lead)
        .where(Lead.brand_id == brand_id, Lead.status != "archived")
        .order_by(
            desc(Lead.status == "hot"),
            desc(Lead.updated_at),
        )
        .limit(3)
    )
    priority_leads = (await session.execute(priority_stmt)).scalars().all()
    for lead in priority_leads:
        name = lead.name or lead.email or "Unknown"
        source = lead.utm_source or lead.source_asset_type or "direct"
        insights.append(f"Priority follow-up: {name} ({lead.status}) — {source}")

    follow_up = None
    if hot > 0:
        follow_up = f"Contact {hot} hot lead(s) before creating new campaigns"
    elif warm > 0:
        follow_up = f"Nurture {warm} warm lead(s) with a direct follow-up"
    elif cold > 0:
        follow_up = f"Re-engage {cold} cold lead(s) with a value-first message"

    return {
        "insights": insights,
        "data_sources": data_sources,
        "has_data": True,
        "follow_up_priority": follow_up,
        "counts": {
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "new": new,
            "lost": lost,
            "total": total,
        },
    }
