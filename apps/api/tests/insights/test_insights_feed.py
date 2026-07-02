"""Module 7 — Insights Feed unit tests (no DB; mocked collectors)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aicmo.modules.insights import ranking, service
from aicmo.modules.insights.schemas import FeedItem


def _item(title="t", *, source="learning", category="channel", severity="medium",
          confidence=60, urgency=None, impact=None, channels=None, objective=None):
    it = FeedItem(
        id=ranking.make_id(source, category, title),
        source_module=source,
        source_label=source,
        link=f"/{source}",
        category=category,
        title=title,
        detail=title,
        why_surfaced="because",
        recommendation="do it",
        expected_result="+x",
        evidence=[],
        confidence=confidence,
        severity=severity,
        urgency=urgency,
        impact_category=impact,
        business_objective=objective,
        channels=channels or [],
        priority_score=0.0,
        group_key=category,
    )
    it.priority_score = ranking.compute_priority(it)
    return it


_TENANT = SimpleNamespace(brand_id="brand-1", organization_id="org-1", user_id="u1")


# --------------------------------------------------------------------------
#  ranking primitives
# --------------------------------------------------------------------------
def test_severity_from_confidence_bands_and_negative_bump():
    assert ranking.severity_from_confidence(90) == "high"
    assert ranking.severity_from_confidence(60) == "medium"
    assert ranking.severity_from_confidence(30) == "low"
    # A negative (failing) lesson is bumped up.
    assert ranking.severity_from_confidence(70, negative=True) == "critical"
    assert ranking.severity_from_confidence(30, negative=True) == "high"


def test_priority_orders_critical_over_low():
    hi = _item("a", severity="critical", urgency="now", confidence=90, impact="revenue")
    lo = _item("b", severity="low", urgency="monitor", confidence=20)
    assert hi.priority_score > lo.priority_score


def test_make_id_stable_and_title_insensitive_to_punct():
    a = ranking.make_id("learning", "channel", "Instagram beats email!")
    b = ranking.make_id("learning", "channel", "instagram beats email")
    assert a == b  # normalised


def test_dedupe_collapses_cross_source_duplicates_keeping_highest():
    a = _item("Instagram beats email", source="learning", severity="high", confidence=85)
    b = _item("instagram beats email!", source="advisor", severity="low", confidence=30)
    out = ranking.dedupe([b, a])
    assert len(out) == 1
    winner = out[0]
    assert winner.severity == "high"  # kept the stronger one
    assert b.id in winner.related_ids  # merged the weaker's id


def test_group_orders_by_top_severity():
    items = [
        _item("x", category="channel", severity="low"),
        _item("y", category="bottleneck", severity="critical"),
    ]
    groups = ranking.group(items)
    assert groups[0].key == "bottleneck"  # most severe group first
    assert groups[0].top_severity == "critical"


def test_meets_min_severity():
    it = _item("x", severity="medium")
    assert ranking.meets_min_severity(it, "low")
    assert ranking.meets_min_severity(it, "medium")
    assert not ranking.meets_min_severity(it, "high")


# --------------------------------------------------------------------------
#  build_feed pipeline
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_build_feed_ranks_dedupes_and_groups(monkeypatch):
    items = [
        _item("Fix landing page", category="conversion", severity="critical", urgency="now"),
        _item("Post more reels", category="channel", severity="low"),
        _item("post more reels", category="channel", severity="low"),  # dup
    ]

    async def fake_collect(_session, *, tenant):
        return items, [], []

    monkeypatch.setattr(service, "collect_all", fake_collect)

    feed = await service.build_feed(None, tenant=_TENANT)

    assert feed.total == 2  # the duplicate collapsed
    assert feed.items[0].title == "Fix landing page"  # critical ranked first
    assert feed.note is None
    assert {g.key for g in feed.groups} == {"conversion", "channel"}


@pytest.mark.asyncio
async def test_build_feed_empty_states_not_enough(monkeypatch):
    async def fake_collect(_session, *, tenant):
        return [], [], []

    monkeypatch.setattr(service, "collect_all", fake_collect)
    feed = await service.build_feed(None, tenant=_TENANT)
    assert feed.total == 0
    assert "Not enough activity" in (feed.note or "")


@pytest.mark.asyncio
async def test_build_feed_min_severity_filter(monkeypatch):
    items = [
        _item("crit", category="c1", severity="critical"),
        _item("low", category="c2", severity="low"),
    ]

    async def fake_collect(_session, *, tenant):
        return items, [], []

    monkeypatch.setattr(service, "collect_all", fake_collect)
    feed = await service.build_feed(None, tenant=_TENANT, min_severity="high")
    assert feed.total == 1
    assert feed.items[0].title == "crit"


@pytest.mark.asyncio
async def test_build_feed_filter_no_match_notes_filters(monkeypatch):
    items = [_item("only-low", category="c1", severity="low")]

    async def fake_collect(_session, *, tenant):
        return items, [], []

    monkeypatch.setattr(service, "collect_all", fake_collect)
    feed = await service.build_feed(None, tenant=_TENANT, min_severity="critical")
    assert feed.total == 0
    assert "filters" in (feed.note or "")
