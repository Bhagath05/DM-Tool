"""Per-content analytics — read-only over SocialAsset + PerformanceSignal.

Reuses the existing per-post store (no new table) plus ScheduledPost attribution
to answer content-level questions: top/worst content, format comparison, and
"which content to repeat". Every claim is gated on how much content exists and
carries computed evidence (the same `Insight`/`MetricEvidence` contract the
advisor already consumes). The LLM may explain these numbers; it never makes
them.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.rules import confidence_band
from aicmo.modules.marketing_analytics.schemas import (
    ContentPerformanceItem,
    ContentPerformanceReport,
    DataSufficiency,
    FormatComparisonRow,
    Insight,
    MetricEvidence,
    RecommendationEffectiveness,
)
from aicmo.modules.publishing.models import ScheduledPost
from aicmo.modules.social.models import PerformanceSignal, SocialAsset

_LOOKBACK_DAYS = 90
_WINDOW = "90d"
# Ranking / median claims need a real sample; below this we stay honest.
_MIN_FOR_RANKING = 5
# A format needs at least this many posts before we call it a pattern.
_MIN_PER_FORMAT = 3
# Need at least this many recommendation-driven posts before comparing them.
_MIN_REC_DRIVEN = 3

# Content asset_type → a valid content generator format (ContentType). Lets a
# "repeat this winning format" insight deep-link into the Creative Studio.
_FORMAT_MAP: dict[str, str] = {
    "reel": "reel",
    "short": "reel",
    "video": "reel",
    "carousel": "carousel",
    "story": "social_post",
    "image": "social_post",
    "post": "social_post",
}


def _content_format(asset_type: str) -> str:
    return _FORMAT_MAP.get(asset_type, "social_post")


def _gen_hint(asset_type: str, platform: str, goal: str) -> dict:
    """A GeneratorHint (target/format/platform/goal) so the recommendation is
    executable — the human still reviews and approves before publishing."""
    return {
        "target": "content",
        "format": _content_format(asset_type),
        "platform": platform,
        "goal": goal,
    }


_SIGNAL_METRIC_FIELDS = (
    "impressions",
    "reach",
    "likes",
    "comments_count",
    "saves",
    "shares",
    "views",
)


@dataclass
class _Item:
    asset: SocialAsset
    signal: PerformanceSignal
    available: list[str] = field(default_factory=list)

    @property
    def engagement_rate(self) -> float:
        return float(self.signal.engagement_rate or 0.0)


def _now() -> datetime:
    return datetime.now(UTC)


def _available_metrics(signal: PerformanceSignal) -> list[str]:
    """Which metrics the provider actually reported. Prefer the explicit list in
    raw_json (written by Phase-5 collection); else infer from non-zero fields."""
    raw = signal.raw_json or {}
    declared = raw.get("metrics")
    if isinstance(declared, dict) and declared:
        return sorted(declared.keys())
    present = [f for f in _SIGNAL_METRIC_FIELDS if int(getattr(signal, f, 0) or 0) > 0]
    return present


async def _load_items(session: AsyncSession, *, brand_id: uuid.UUID) -> list[_Item]:
    cutoff = _now() - timedelta(days=_LOOKBACK_DAYS)
    asset_rows = (
        (
            await session.execute(
                select(SocialAsset)
                .where(
                    SocialAsset.brand_id == brand_id,
                    func.coalesce(SocialAsset.posted_at, SocialAsset.created_at) >= cutoff,
                )
                .order_by(desc(func.coalesce(SocialAsset.posted_at, SocialAsset.created_at)))
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    if not asset_rows:
        return []

    # Latest PerformanceSignal per asset (a post's metrics change over time).
    latest: dict[uuid.UUID, PerformanceSignal] = {}
    signal_rows = (
        (
            await session.execute(
                select(PerformanceSignal)
                .where(PerformanceSignal.asset_id.in_([a.id for a in asset_rows]))
                .order_by(desc(PerformanceSignal.captured_at))
            )
        )
        .scalars()
        .all()
    )
    for s in signal_rows:
        latest.setdefault(s.asset_id, s)

    items: list[_Item] = []
    for a in asset_rows:
        sig = latest.get(a.id)
        if sig is None:
            continue  # no metrics collected yet → not rankable
        available = _available_metrics(sig)
        if not available and not sig.engagement_rate:
            continue  # nothing real to show
        items.append(_Item(asset=a, signal=sig, available=available))
    return items


def _assess(n: int) -> tuple[str, str]:
    if n == 0:
        return "none", "No published content with performance data yet."
    if n < _MIN_FOR_RANKING:
        return (
            "short_term",
            "Only a few pieces of content so far — not enough to compare formats reliably.",
        )
    if n < 15:
        return "weekly", ""
    return "strong", ""


def _to_item_schema(it: _Item, *, median: float | None) -> ContentPerformanceItem:
    a, s = it.asset, it.signal
    return ContentPerformanceItem(
        asset_id=str(a.id),
        platform=a.platform,
        platform_label=normalize.provider_label(a.provider_slug or a.platform),
        provider_slug=a.provider_slug,
        platform_post_id=a.platform_post_id,
        asset_type=a.asset_type,
        caption=a.caption,
        permalink=a.permalink,
        thumbnail_url=a.thumbnail_url,
        posted_at=a.posted_at.isoformat() if a.posted_at else None,
        engagement_rate=it.engagement_rate,
        reach=int(s.reach or 0),
        impressions=int(s.impressions or 0),
        views=int(s.views or 0),
        likes=int(s.likes or 0),
        comments=int(s.comments_count or 0),
        shares=int(s.shares or 0),
        saves=int(s.saves or 0),
        available_metrics=it.available,
        above_median=(median is not None and it.engagement_rate > median),
    )


def _format_rows(items: list[_Item]) -> list[FormatComparisonRow]:
    by_type: dict[str, list[_Item]] = defaultdict(list)
    for it in items:
        by_type[it.asset.asset_type].append(it)
    rows: list[FormatComparisonRow] = []
    for atype, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        reaches = [int(g.signal.reach or 0) for g in group if int(g.signal.reach or 0) > 0]
        views = [int(g.signal.views or 0) for g in group if int(g.signal.views or 0) > 0]
        rows.append(
            FormatComparisonRow(
                asset_type=atype,
                count=len(group),
                median_engagement_rate=round(
                    statistics.median(g.engagement_rate for g in group), 4
                ),
                avg_reach=round(sum(reaches) / len(reaches), 1) if reaches else None,
                avg_views=round(sum(views) / len(views), 1) if views else None,
            )
        )
    return rows


def _evidence(*, label: str, platform: str, current: float, median: float) -> MetricEvidence:
    change = round((current - median) / median * 100, 1) if median else None
    return MetricEvidence(
        metric=normalize.ENGAGEMENT_RATE,
        label=label,
        platform=platform,
        current=round(current, 4),
        previous=round(median, 4),
        absolute_change=round(current - median, 4),
        change_percent=change,
        window=_WINDOW,
    )


def _content_insights(items: list[_Item], *, median: float | None, level: str) -> list[Insight]:
    """Deterministic, evidence-backed content recommendations. Fires only with
    a real sample (weekly/strong) and a real median."""
    if level not in ("weekly", "strong") or not median or median <= 0:
        return []
    cap = 85 if level == "strong" else 70
    insights: list[Insight] = []

    # R-C1 — a format is outperforming the recent median engagement.
    by_type: dict[str, list[_Item]] = defaultdict(list)
    for it in items:
        by_type[it.asset.asset_type].append(it)
    for atype, group in by_type.items():
        if len(group) < _MIN_PER_FORMAT:
            continue
        gmed = statistics.median(g.engagement_rate for g in group)
        above = sum(1 for g in group if g.engagement_rate > median)
        if gmed > median * 1.2 and above >= _MIN_PER_FORMAT:
            platform = normalize.provider_label(
                group[0].asset.provider_slug or group[0].asset.platform
            )
            conf = min(68, cap)
            insights.append(
                Insight(
                    id=f"content_format_outperforms:{atype}",
                    severity="good",
                    observation=(
                        f"Your {atype} content is outperforming your recent median engagement — "
                        f"{above} of {len(group)} recent {atype} posts are above it."
                    ),
                    evidence=[
                        _evidence(
                            label=f"{atype} engagement rate",
                            platform=platform,
                            current=gmed,
                            median=median,
                        )
                    ],
                    interpretation=(
                        f"{atype.title()} is resonating more than your typical post right now."
                    ),
                    recommendation=f"Repeat this format — make more {atype} content using your recent winners as the template.",
                    reason=f"{atype} median engagement above overall median ({_WINDOW}).",
                    confidence=conf,
                    confidence_band=confidence_band(conf),
                    expected_result="Higher average engagement if you keep leaning into this format.",
                    impact_category="lead",
                    window=_WINDOW,
                    generator_hint=_gen_hint(
                        atype, platform, f"Repeat your winning {atype} format"
                    ),
                )
            )

    # R-C2 — a standout individual post well above the median.
    top = max(items, key=lambda i: i.engagement_rate)
    if top.engagement_rate > median * 1.5:
        a = top.asset
        platform = normalize.provider_label(a.provider_slug or a.platform)
        conf = min(64, cap)
        label = (a.caption or a.asset_type)[:60]
        insights.append(
            Insight(
                id=f"content_standout:{a.id}",
                severity="good",
                observation=(
                    f"Your {platform} {a.asset_type} “{label}” generated well above your "
                    "recent median engagement."
                ),
                evidence=[
                    _evidence(
                        label=f"{a.asset_type} engagement rate",
                        platform=platform,
                        current=top.engagement_rate,
                        median=median,
                    )
                ],
                interpretation="This specific post struck a chord with your audience.",
                recommendation="Repeat this content's hook and format in your next few posts.",
                reason=f"Top post engagement >1.5x median ({_WINDOW}).",
                confidence=conf,
                confidence_band=confidence_band(conf),
                expected_result="A repeat of the outperformance if the hook/format is reused.",
                impact_category="lead",
                window=_WINDOW,
                generator_hint=_gen_hint(
                    a.asset_type, platform, "Repeat this winning post's format"
                ),
            )
        )
    return insights


async def _rec_driven_post_ids(
    session: AsyncSession, *, brand_id: uuid.UUID, post_ids: list[str]
) -> set[str]:
    """platform_post_ids whose ScheduledPost carries a recommendation_id — i.e.
    content that came from an AI recommendation. Tenant-scoped by brand_id."""
    if not post_ids:
        return set()
    rows = (
        (
            await session.execute(
                select(ScheduledPost.platform_post_id).where(
                    ScheduledPost.brand_id == brand_id,
                    ScheduledPost.platform_post_id.in_(post_ids),
                    ScheduledPost.recommendation_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {r for r in rows if r}


def _rec_effectiveness(
    items: list[_Item], *, rec_ids: set[str], median: float
) -> RecommendationEffectiveness:
    """Honest comparison — reports what the data shows, never claims causation."""
    rec = [i for i in items if i.asset.platform_post_id in rec_ids]
    other = [i for i in items if i.asset.platform_post_id not in rec_ids]
    if len(rec) < _MIN_REC_DRIVEN:
        return RecommendationEffectiveness(
            has_data=False,
            recommendation_driven_count=len(rec),
            other_count=len(other),
            summary="Not enough recommendation-driven content yet to compare.",
        )
    rec_med = round(statistics.median(i.engagement_rate for i in rec), 4)
    other_med = round(statistics.median(i.engagement_rate for i in other), 4) if other else None
    vs = round((rec_med - median) / median * 100, 1) if median else None
    if vs is None:
        summary = f"{len(rec)} recommendation-driven posts collected."
    else:
        direction = "above" if vs >= 0 else "below"
        summary = (
            f"Recommendation-driven content performed {abs(vs):.0f}% {direction} your recent "
            f"median engagement ({len(rec)} posts). This is an observation, not proof of cause."
        )
    return RecommendationEffectiveness(
        has_data=True,
        recommendation_driven_count=len(rec),
        other_count=len(other),
        recommendation_median_engagement=rec_med,
        other_median_engagement=other_med,
        vs_overall_percent=vs,
        summary=summary,
    )


async def content_report(session: AsyncSession, *, brand_id: uuid.UUID) -> ContentPerformanceReport:
    """Full per-content report for the API/frontend."""
    items = await _load_items(session, brand_id=brand_id)
    level, message = _assess(len(items))
    generated_at = _now().isoformat()
    sufficiency = DataSufficiency(
        level=level,
        days_covered=len({i.asset.posted_at.date() for i in items if i.asset.posted_at}),
        observations=len(items),
        message=message,
    )
    if not items:
        return ContentPerformanceReport(
            has_data=False,
            sufficiency=sufficiency,
            window=_WINDOW,
            generated_at=generated_at,
        )

    rates = [i.engagement_rate for i in items]
    median = statistics.median(rates)
    ranked = sorted(items, key=lambda i: i.engagement_rate, reverse=True)
    top = [_to_item_schema(i, median=median) for i in ranked[:5]]
    worst = (
        [_to_item_schema(i, median=median) for i in ranked[-3:][::-1]]
        if len(items) >= _MIN_FOR_RANKING
        else []
    )
    insights = _content_insights(items, median=median, level=level)
    rec_ids = await _rec_driven_post_ids(
        session, brand_id=brand_id, post_ids=[i.asset.platform_post_id for i in items]
    )
    return ContentPerformanceReport(
        has_data=True,
        sufficiency=sufficiency,
        window=_WINDOW,
        median_engagement_rate=round(median, 4),
        top=top,
        worst=worst,
        format_comparison=_format_rows(items),
        insights=insights,
        recommendation_effectiveness=_rec_effectiveness(items, rec_ids=rec_ids, median=median),
        generated_at=generated_at,
    )


async def content_signal(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[list[Insight], list[ContentPerformanceItem]]:
    """Compact content evidence for the advisor signal: (insights, top items).
    Returns empty when there isn't enough content to make an honest claim."""
    items = await _load_items(session, brand_id=brand_id)
    level, _ = _assess(len(items))
    if not items:
        return [], []
    median = statistics.median(i.engagement_rate for i in items)
    insights = _content_insights(items, median=median, level=level)
    ranked = sorted(items, key=lambda i: i.engagement_rate, reverse=True)
    top = [_to_item_schema(i, median=median) for i in ranked[:3]]
    return insights, top
