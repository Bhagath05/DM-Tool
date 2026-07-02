"""Phase 4.5 — operations → Learning Engine signal summariser (real rows only)."""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.operations import learning_feed


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Serves learning_signals' three queries in order: work, events, goals."""

    def __init__(self, work, events, goals):
        self._batches = [work, events, goals]
        self._i = 0

    async def execute(self, *a, **k):
        batch = self._batches[self._i]
        self._i += 1
        return _FakeResult(batch)


@pytest.mark.asyncio
async def test_empty_history_yields_no_signals():
    session = _FakeSession(work=[], events=[], goals=[])
    lines = await learning_feed.learning_signals(session, brand_id=uuid.uuid4())
    assert lines == []


@pytest.mark.asyncio
async def test_approval_preferences_summarised():
    work = [
        ("content_generation", "approved"),
        ("content_generation", "queued"),
        ("email", "dismissed"),
        ("email", "dismissed"),
    ]
    session = _FakeSession(work=work, events=[], goals=[])
    lines = await learning_feed.learning_signals(session, brand_id=uuid.uuid4())
    joined = " ".join(lines)
    assert "APPROVED" in joined and "content_generation" in joined
    assert "DISMISSED" in joined and "email" in joined


@pytest.mark.asyncio
async def test_recurring_events_and_achieved_goals():
    events = [("no_recent_leads",), ("no_recent_leads",), ("traffic_drop",)]  # one recurs
    goals = [("Grow leads", "achieved"), ("Grow traffic", "active")]
    session = _FakeSession(work=[], events=events, goals=goals)
    lines = await learning_feed.learning_signals(session, brand_id=uuid.uuid4())
    joined = " ".join(lines)
    assert "Recurring detected events" in joined and "no_recent_leads x2" in joined
    assert "traffic_drop" not in joined  # only appeared once → not recurring
    assert "Goals achieved" in joined and "Grow leads" in joined
