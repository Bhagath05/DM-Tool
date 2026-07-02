"""Phase 4.2 — Event Detection tests (pure rules + dedupe; no DB)."""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.operations import events


def _types(drafts):
    return {d.event_type for d in drafts}


# --------------------------------------------------------------------------
#  Pure detection rules
# --------------------------------------------------------------------------
def test_no_recent_leads():
    d = events.detect({"leads_7d": 0}, {"leads_7d": 6})
    assert "no_recent_leads" in _types(d)
    ev = next(x for x in d if x.event_type == "no_recent_leads")
    assert ev.severity == "high" and ev.direction == "negative"


def test_leads_declining_vs_surge():
    assert "leads_declining" in _types(events.detect({"leads_7d": 4}, {"leads_7d": 10}))
    assert "leads_surge" in _types(events.detect({"leads_7d": 12}, {"leads_7d": 5}))


def test_traffic_spike_and_drop():
    assert "traffic_spike" in _types(events.detect({"total_views": 200}, {"total_views": 100}))
    assert "traffic_drop" in _types(events.detect({"total_views": 40}, {"total_views": 120}))


def test_conversion_drop():
    d = events.detect({"conversion_rate": 0.02}, {"conversion_rate": 0.05})
    assert "conversion_drop" in _types(d)


def test_publishing_failures_and_performance_flagged():
    d = events.detect(
        {"failed_posts": 3, "performance_diagnostics": 2},
        {"failed_posts": 1, "performance_diagnostics": 0},
    )
    assert {"publishing_failures", "performance_flagged"} <= _types(d)


def test_no_events_on_stable_metrics():
    same = {"leads_7d": 5, "total_views": 100, "conversion_rate": 0.03, "failed_posts": 0}
    assert events.detect(same, same) == []


def test_small_numbers_dont_trigger_noise():
    # 1 → 0 leads is below the "had >=3" bar for no_recent_leads.
    assert "no_recent_leads" not in _types(events.detect({"leads_7d": 0}, {"leads_7d": 1}))
    # tiny traffic change is ignored (abs threshold).
    assert "traffic_spike" not in _types(events.detect({"total_views": 5}, {"total_views": 2}))


# --------------------------------------------------------------------------
#  Persistence dedupe
# --------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, active_types=()):
        self.added = []
        self._active = [(t,) for t in active_types]

    async def execute(self, *a, **k):
        return _FakeResult(self._active)

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_detect_and_store_persists_new_events():
    session = _FakeSession(active_types=())
    created = await events.detect_and_store(
        session,
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        current={"leads_7d": 0},
        previous={"leads_7d": 8},
    )
    assert len(created) == 1
    assert created[0].event_type == "no_recent_leads"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_detect_and_store_dedupes_against_open_events():
    # An open no_recent_leads already exists → don't re-emit.
    session = _FakeSession(active_types=("no_recent_leads",))
    created = await events.detect_and_store(
        session,
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        current={"leads_7d": 0},
        previous={"leads_7d": 8},
    )
    assert created == []
    assert session.added == []
