"""Phase 5 — per-content analytics read layer (fake session, no live DB)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from aicmo.modules.marketing_analytics import content, normalize

NOW = datetime.now(UTC)
BRAND = uuid.uuid4()


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Sess:
    def __init__(self, assets, signals):
        self._assets = assets
        self._signals = signals
        self.captured: dict[str, object] = {}

    async def execute(self, stmt):
        s = str(stmt)
        if "social_assets" in s:
            self.captured["assets"] = stmt
            return _Res(self._assets)
        if "performance_signals" in s:
            return _Res(self._signals)
        return _Res([])


def _pair(
    asset_type,
    engagement_rate,
    *,
    reach=1000,
    likes=50,
    day=1,
    provider="instagram_organic",
    raw=None,
):
    aid = uuid.uuid4()
    asset = SimpleNamespace(
        id=aid,
        platform="instagram" if provider == "instagram_organic" else provider,
        provider_slug=provider if provider != "instagram_organic" else None,
        platform_post_id=f"post-{aid.hex[:6]}",
        asset_type=asset_type,
        caption=f"{asset_type} caption",
        permalink=None,
        thumbnail_url=None,
        posted_at=NOW - timedelta(days=day),
        created_at=NOW - timedelta(days=day),
        brand_id=BRAND,
    )
    signal = SimpleNamespace(
        id=uuid.uuid4(),
        asset_id=aid,
        impressions=0,
        reach=reach,
        likes=likes,
        comments_count=0,
        saves=0,
        shares=0,
        engagement_rate=engagement_rate,
        views=0,
        watch_time_seconds=0.0,
        ctr=0.0,
        raw_json=raw if raw is not None else {},
        captured_at=NOW - timedelta(hours=1),
    )
    return asset, signal


def _dataset(pairs):
    return _Sess([a for a, _ in pairs], [s for _, s in pairs])


# 3 winning reels + 3 weak images → clear format winner.
def _reels_vs_images():
    pairs = [_pair("reel", 0.10, day=i) for i in range(3)]
    pairs += [_pair("image", 0.02, day=3 + i) for i in range(3)]
    return pairs


# ---------------- empty / insufficient ----------------


@pytest.mark.asyncio
async def test_empty_when_no_content():
    report = await content.content_report(_Sess([], []), brand_id=BRAND)
    assert report.has_data is False
    assert report.sufficiency.level == "none"
    assert report.top == [] and report.insights == []


@pytest.mark.asyncio
async def test_insufficient_history_yields_no_insights():
    report = await content.content_report(
        _dataset([_pair("reel", 0.1, day=i) for i in range(4)]), brand_id=BRAND
    )
    assert report.has_data is True
    assert report.sufficiency.level == "short_term"
    assert report.insights == []  # <5 items → no ranking/format claims


# ---------------- ranking + comparison ----------------


@pytest.mark.asyncio
async def test_ranks_top_and_worst():
    report = await content.content_report(_dataset(_reels_vs_images()), brand_id=BRAND)
    assert report.has_data is True
    assert report.top[0].engagement_rate == 0.10  # best first
    assert report.worst[0].engagement_rate == 0.02  # weakest first
    assert report.median_engagement_rate == 0.06
    assert report.top[0].above_median is True


@pytest.mark.asyncio
async def test_format_comparison_groups_by_asset_type():
    report = await content.content_report(_dataset(_reels_vs_images()), brand_id=BRAND)
    by_type = {r.asset_type: r for r in report.format_comparison}
    assert by_type["reel"].count == 3 and by_type["image"].count == 3
    assert by_type["reel"].median_engagement_rate > by_type["image"].median_engagement_rate


# ---------------- content insights + evidence integrity ----------------


@pytest.mark.asyncio
async def test_format_outperformance_insight_fires():
    report = await content.content_report(_dataset(_reels_vs_images()), brand_id=BRAND)
    hit = [i for i in report.insights if i.id.startswith("content_format_outperforms")]
    assert len(hit) == 1
    assert hit[0].severity == "good"
    assert "reel" in hit[0].recommendation.lower()
    # evidence is computed engagement rate vs the real median (never fabricated)
    ev = hit[0].evidence[0]
    assert ev.metric == normalize.ENGAGEMENT_RATE
    assert ev.previous == 0.06 and ev.current == 0.10


@pytest.mark.asyncio
async def test_standout_content_insight_references_a_specific_post():
    report = await content.content_report(_dataset(_reels_vs_images()), brand_id=BRAND)
    hit = [i for i in report.insights if i.id.startswith("content_standout")]
    assert hit  # top post 0.10 > median 0.06 * 1.5
    assert hit[0].evidence[0].current == 0.10


@pytest.mark.asyncio
async def test_available_metrics_honesty():
    # explicit provider list → exactly those keys
    pairs = [
        _pair("reel", 0.1, day=i, raw={"metrics": {"views": 100, "likes": 5}}) for i in range(5)
    ]
    report = await content.content_report(_dataset(pairs), brand_id=BRAND)
    assert report.top[0].available_metrics == ["likes", "views"]
    # no explicit list → inferred from non-zero fields (reach + likes set above)
    report2 = await content.content_report(_dataset(_reels_vs_images()), brand_id=BRAND)
    assert set(report2.top[0].available_metrics) == {"reach", "likes"}


# ---------------- signal + tenant isolation ----------------


@pytest.mark.asyncio
async def test_content_signal_returns_insights_and_top():
    insights, top = await content.content_signal(_dataset(_reels_vs_images()), brand_id=BRAND)
    assert insights and len(top) <= 3
    assert top[0].engagement_rate == 0.10


@pytest.mark.asyncio
async def test_query_scoped_to_brand():
    sess = _dataset(_reels_vs_images())
    await content.content_report(sess, brand_id=BRAND)
    sql = sess.captured["assets"].compile(dialect=postgresql.dialect())
    assert "brand_id" in str(sql) and BRAND in sql.params.values()
