"""Content Intelligence — performance-derived insights for the advisor."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.schemas import DataSourceRef
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.learning.models import LearningEvent
from aicmo.modules.social.models import WinningPattern


async def load_content_intelligence(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> dict:
    """Real performance data only — best types, platforms, posting patterns."""
    insights: list[str] = []
    data_sources: list[DataSourceRef] = []

    top_assets = await analytics_service.top_assets(session, brand_id=brand_id, limit=5)
    if top_assets.items:
        best = top_assets.items[0]
        insights.append(
            f"Top converting asset: {best.source_asset_type}/{best.subtype} "
            f"with {best.leads} leads ({best.hot_leads} hot)"
        )
        data_sources.append(
            DataSourceRef(
                key=f"top_asset:{best.source_asset_id}",
                label="Top asset leads",
                value=str(best.leads),
            )
        )
        by_type: Counter[str] = Counter()
        by_platform: Counter[str] = Counter()
        for row in top_assets.items:
            by_type[row.subtype] += row.leads
            if row.platform:
                by_platform[row.platform] += row.leads
        if by_type:
            best_type, type_leads = by_type.most_common(1)[0]
            insights.append(f"Best content type by leads: {best_type} ({type_leads} leads)")
        if by_platform:
            best_plat, plat_leads = by_platform.most_common(1)[0]
            insights.append(f"Best platform by leads: {best_plat} ({plat_leads} leads)")

    pattern_stmt = (
        select(WinningPattern)
        .where(WinningPattern.brand_id == brand_id)
        .order_by(desc(WinningPattern.performance_score))
        .limit(5)
    )
    patterns = (await session.execute(pattern_stmt)).scalars().all()
    for p in patterns:
        if p.posting_time_pattern:
            insights.append(
                f"Winning pattern on {p.platform or 'all'}: "
                f"{p.summary[:80]} — best time: {p.posting_time_pattern}"
            )
            data_sources.append(
                DataSourceRef(
                    key=f"pattern:{p.id}",
                    label=f"{p.platform or 'platform'} posting time",
                    value=p.posting_time_pattern,
                )
            )
        elif p.summary:
            insights.append(
                f"Winning pattern: {p.summary} (score {float(p.performance_score):.0%})"
            )

    learning_stmt = (
        select(LearningEvent)
        .where(
            LearningEvent.brand_id == brand_id,
            LearningEvent.status == "active",
            LearningEvent.confidence_score >= 0.4,
        )
        .order_by(desc(LearningEvent.confidence_score))
        .limit(5)
    )
    events = (await session.execute(learning_stmt)).scalars().all()
    for ev in events:
        insights.append(f"Learned ({ev.variable}): {ev.finding}")

    content_count = (
        await session.execute(
            select(func.count())
            .select_from(GeneratedContent)
            .where(GeneratedContent.brand_id == brand_id)
        )
    ).scalar_one()
    if content_count == 0:
        insights.append("No generated content yet — cannot recommend formats from performance.")

    creative_formats = _suggest_creative_formats(insights, patterns)
    return {
        "insights": insights,
        "data_sources": data_sources,
        "has_data": len(insights) > 0,
        "creative_formats": creative_formats,
    }


def _suggest_creative_formats(insights: list[str], patterns: list) -> list[str]:
    """Map performance signals to creative studio formats — evidence only."""
    formats: list[str] = []
    text = " ".join(insights).lower()
    if "reel" in text or any(
        (getattr(p, "format_pattern") or "").lower().find("reel") >= 0 for p in patterns
    ):
        formats.append("reel")
    if "carousel" in text:
        formats.append("carousel")
    if "story" in text:
        formats.append("story")
    if "whatsapp" in text:
        formats.append("whatsapp")
    if "banner" in text or "ad" in text:
        formats.append("banner")
    if "brochure" in text:
        formats.append("brochure")
    if "poster" in text or not formats:
        formats.append("poster")
    return formats[:5]
