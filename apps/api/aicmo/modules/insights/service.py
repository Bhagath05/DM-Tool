"""Module 7 — Insights Feed orchestrator.

Pure pipeline over already-collected outputs: score → dedupe → rank → filter →
group. Generates nothing new.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.insights import ranking
from aicmo.modules.insights.aggregator import collect_all
from aicmo.modules.insights.schemas import InsightFeedResponse
from aicmo.tenancy.context import TenantContext


async def build_feed(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    category: str | None = None,
    min_severity: str | None = None,
    channel: str | None = None,
    objective: str | None = None,
) -> InsightFeedResponse:
    items, sources, live_surfaces = await collect_all(session, tenant=tenant)

    # Score, then collapse cross-source duplicates, then rank.
    for it in items:
        it.priority_score = ranking.compute_priority(it)
    items = ranking.dedupe(items)
    items = ranking.rank(items)

    # Filters (applied after ranking so the grouped view reflects them).
    filters_applied = {
        "category": category,
        "min_severity": min_severity,
        "channel": channel,
        "objective": objective,
    }
    had_before = len(items)
    if category:
        items = [i for i in items if i.category == category]
    if min_severity:
        items = [i for i in items if ranking.meets_min_severity(i, min_severity)]
    if channel:
        items = [i for i in items if channel in i.channels]
    if objective:
        items = [i for i in items if i.business_objective == objective]

    groups = ranking.group(items)

    note: str | None = None
    if not items:
        if had_before and any(v for v in filters_applied.values()):
            note = "No insights match these filters — try clearing them."
        else:
            note = (
                "Not enough activity yet to surface insights. As your strategy, "
                "posts, and results accumulate, this feed fills up automatically."
            )

    return InsightFeedResponse(
        items=items,
        groups=groups,
        total=len(items),
        sources=sources,
        live_surfaces=live_surfaces,
        filters_applied=filters_applied,
        generated_at=datetime.now(UTC).isoformat(),
        note=note,
    )
