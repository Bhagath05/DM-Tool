"""Phase 5 — per-content evidence flows into the advisor signal + prompt."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from aicmo.modules.marketing_analytics import service
from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    ContentPerformanceItem,
    Insight,
    MetricEvidence,
)
from aicmo.modules.marketing_analytics.signal_prompt import signal_to_prompt_block

NOW = datetime.now(UTC)
BRAND = uuid.uuid4()


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Sess:
    """Routes connector_metrics / integration_connection / social_assets /
    performance_signals reads by the compiled SQL."""

    def __init__(self, *, assets, signals, conns):
        self._assets = assets
        self._signals = signals
        self._conns = conns

    async def execute(self, stmt):
        # Order matters: the social_assets SELECT lists the integration_connection_id
        # column, so match the specific tables before the connection lookup.
        s = str(stmt)
        if "social_assets" in s:
            return _Res(self._assets)
        if "performance_signals" in s:
            return _Res(self._signals)
        if "connector_metrics" in s:
            return _Res([])  # no account-level metrics in this scenario
        if "integration_connection" in s:
            return _Res(self._conns)
        return _Res([])


def _pair(asset_type, rate, day):
    aid = uuid.uuid4()
    asset = SimpleNamespace(
        id=aid,
        platform="instagram",
        provider_slug=None,
        platform_post_id=f"p{aid.hex[:5]}",
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


def _reels_vs_images():
    pairs = [_pair("reel", 0.10, i) for i in range(3)]
    pairs += [_pair("image", 0.02, 3 + i) for i in range(3)]
    return pairs


@pytest.mark.asyncio
async def test_advisor_signal_carries_content_even_without_account_metrics():
    pairs = _reels_vs_images()
    sess = _Sess(
        assets=[a for a, _ in pairs],
        signals=[s for _, s in pairs],
        conns=[SimpleNamespace(id=uuid.uuid4())],  # connected
    )
    signal = await service.advisor_signal(sess, brand_id=BRAND)
    # account-level empty, but per-content evidence is present + specific
    assert signal.has_data is False
    assert signal.content_insights, "expected content insights"
    assert signal.top_content and signal.top_content[0].engagement_rate == 0.10
    assert any(i.id.startswith("content_format_outperforms") for i in signal.content_insights)


# ---------------- prompt rendering ----------------


def _content_insight():
    return Insight(
        id="content_format_outperforms:reel",
        severity="good",
        observation="Your reel content is outperforming your recent median engagement — 3 of 3 above it.",
        evidence=[
            MetricEvidence(
                metric="engagement_rate",
                label="reel engagement rate",
                platform="Instagram",
                current=0.10,
                previous=0.06,
                change_percent=66.7,
                window="90d",
            )
        ],
        interpretation="Reels resonate more than your typical post.",
        recommendation="Repeat this format — make more reel content.",
        reason="reel median above overall median",
        confidence=68,
        confidence_band="medium",
        expected_result="Higher average engagement.",
        impact_category="lead",
        window="90d",
    )


def _top_item():
    return ContentPerformanceItem(
        asset_id="a1",
        platform="instagram",
        platform_label="Instagram",
        platform_post_id="p1",
        asset_type="reel",
        engagement_rate=0.10,
        reach=1000,
        impressions=0,
        views=0,
        likes=50,
        comments=0,
        shares=0,
        saves=0,
        available_metrics=["reach", "likes"],
        above_median=True,
    )


def _signal(has_data: bool):
    return AdvisorAnalyticsSignal(
        has_data=has_data,
        connected=True,
        data_sufficiency="weekly" if has_data else "none",
        window="7d",
        headline="hi",
        empty_message=None if has_data else "connected, no account metrics",
        content_insights=[_content_insight()],
        top_content=[_top_item()],
    )


def test_prompt_renders_content_findings_on_main_path():
    block = signal_to_prompt_block(_signal(has_data=True))
    assert "Content-level findings" in block
    assert "reel content is outperforming" in block
    assert "Top content so far: Instagram reel" in block


def test_prompt_renders_content_even_without_account_data():
    block = signal_to_prompt_block(_signal(has_data=False))
    assert "Content-level findings" in block
    assert (
        "never invent or\nchange" in block or "never invent" in block
    )  # content guardrail present


def test_prompt_content_uses_only_computed_numbers():
    """The prompt must carry the computed engagement figure, not a fabricated one."""
    block = signal_to_prompt_block(_signal(has_data=True))
    assert "10.0%" in block  # top content engagement 0.10 → 10.0%
    assert "42%" not in block
