"""Phase 6 — executable content insights + recommendation-driven analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from aicmo.modules.content.schemas import ContentType
from aicmo.modules.marketing_analytics import content
from aicmo.modules.opportunities.schemas import GeneratorHint

NOW = datetime.now(UTC)
BRAND = uuid.uuid4()
_VALID_CONTENT_TYPES = set(ContentType.__args__)  # type: ignore[attr-defined]


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Sess:
    def __init__(self, assets, signals, rec_post_ids=None):
        self._assets = assets
        self._signals = signals
        self._rec = rec_post_ids or []
        self.captured: dict[str, object] = {}

    async def execute(self, stmt):
        s = str(stmt)
        if "social_assets" in s:
            self.captured["assets"] = stmt
            return _Res(self._assets)
        if "performance_signals" in s:
            return _Res(self._signals)
        if "scheduled_posts" in s:
            self.captured["scheduled"] = stmt
            return _Res(self._rec)
        return _Res([])


def _pair(asset_type, rate, *, post_id, day=1):
    aid = uuid.uuid4()
    asset = SimpleNamespace(
        id=aid,
        platform="instagram",
        provider_slug=None,
        platform_post_id=post_id,
        asset_type=asset_type,
        caption="cap",
        permalink=None,
        thumbnail_url=None,
        posted_at=NOW - timedelta(days=day),
        created_at=NOW - timedelta(days=day),
        brand_id=BRAND,
    )
    sig = SimpleNamespace(
        id=uuid.uuid4(),
        asset_id=aid,
        impressions=0,
        reach=1000,
        likes=50,
        comments_count=0,
        saves=0,
        shares=0,
        engagement_rate=rate,
        views=0,
        watch_time_seconds=0.0,
        ctr=0.0,
        raw_json={},
        captured_at=NOW,
    )
    return asset, sig


# 3 winning reels + 3 weak images
def _dataset(rec_reels=False):
    reels = [_pair("reel", 0.10, post_id=f"reel{i}", day=i) for i in range(3)]
    images = [_pair("image", 0.02, post_id=f"img{i}", day=3 + i) for i in range(3)]
    pairs = reels + images
    rec_ids = [f"reel{i}" for i in range(3)] if rec_reels else []
    return _Sess([a for a, _ in pairs], [s for _, s in pairs], rec_post_ids=rec_ids)


# ---------------- executable content insight ----------------


@pytest.mark.asyncio
async def test_content_insight_carries_valid_generator_hint():
    report = await content.content_report(_dataset(), brand_id=BRAND)
    fmt = [i for i in report.insights if i.id.startswith("content_format_outperforms")]
    assert fmt and fmt[0].generator_hint is not None
    hint = GeneratorHint.model_validate(fmt[0].generator_hint)  # must validate
    assert hint.target == "content"
    assert hint.format in _VALID_CONTENT_TYPES  # deep-links into a real generator
    assert hint.format == "reel"  # winning format preserved


@pytest.mark.asyncio
async def test_standout_insight_is_also_executable():
    report = await content.content_report(_dataset(), brand_id=BRAND)
    standout = [i for i in report.insights if i.id.startswith("content_standout")]
    assert standout and standout[0].generator_hint is not None
    GeneratorHint.model_validate(standout[0].generator_hint)


# ---------------- recommendation-driven analytics ----------------


@pytest.mark.asyncio
async def test_recommendation_effectiveness_compares_honestly():
    report = await content.content_report(_dataset(rec_reels=True), brand_id=BRAND)
    eff = report.recommendation_effectiveness
    assert eff is not None and eff.has_data is True
    assert eff.recommendation_driven_count == 3 and eff.other_count == 3
    # the winning reels are the recommendation-driven ones → above median
    assert eff.recommendation_median_engagement > eff.other_median_engagement
    assert eff.vs_overall_percent is not None and eff.vs_overall_percent > 0
    assert "above your recent median" in eff.summary
    # honest framing — never claims causation
    assert "not proof of cause" in eff.summary
    assert "caused" not in eff.summary.lower()


@pytest.mark.asyncio
async def test_recommendation_effectiveness_insufficient_is_honest():
    report = await content.content_report(_dataset(rec_reels=False), brand_id=BRAND)
    eff = report.recommendation_effectiveness
    assert eff is not None and eff.has_data is False
    assert "Not enough recommendation-driven content" in eff.summary


@pytest.mark.asyncio
async def test_recommendation_attribution_query_scoped_to_brand():
    sess = _dataset(rec_reels=True)
    await content.content_report(sess, brand_id=BRAND)
    sql = sess.captured["scheduled"].compile(dialect=postgresql.dialect())
    assert "brand_id" in str(sql) and BRAND in sql.params.values()
    # attribution keys on recommendation_id (recommendation-driven content only)
    assert "recommendation_id" in str(sql)
