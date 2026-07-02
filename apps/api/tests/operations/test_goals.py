"""Phase 4.3 — Autonomous Goal Engine tests (pure progress + measurement)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.operations import goals


def _goal(**over):
    base = dict(
        metric="leads",
        goal_type="increase",
        target_value=100.0,
        baseline_value=20.0,
        current_value=20.0,
        measurable=True,
        status="active",
        title="Get to 100 leads",
        achieved_at=None,
        last_measured_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------
#  Metric mapping / measurability
# --------------------------------------------------------------------------
def test_measurable_vs_unmeasured_metrics():
    assert goals.is_measurable("leads") is True
    assert goals.snapshot_key_for("website_traffic") == "total_views"
    # Metrics we don't capture yet are honestly not measurable.
    assert goals.is_measurable("roas") is False
    assert goals.is_measurable("instagram_followers") is False
    assert goals.snapshot_key_for("cpa") is None


# --------------------------------------------------------------------------
#  Progress math
# --------------------------------------------------------------------------
def test_progress_increase():
    g = _goal(baseline_value=20, current_value=60, target_value=100)
    assert goals.progress_fraction(g) == pytest.approx(0.5)  # (60-20)/(100-20)


def test_progress_clamped_and_achieved():
    g = _goal(current_value=120, target_value=100)
    assert goals.progress_fraction(g) == 1.0  # clamped
    assert goals.is_achieved(g) is True


def test_progress_decrease_goal():
    g = _goal(goal_type="decrease", baseline_value=100, current_value=70, target_value=50)
    assert goals.progress_fraction(g) == pytest.approx(0.6)  # (100-70)/(100-50)
    assert goals.is_achieved(g) is False
    g2 = _goal(goal_type="decrease", baseline_value=100, current_value=40, target_value=50)
    assert goals.is_achieved(g2) is True


def test_unmeasurable_goal_has_no_progress():
    g = _goal(metric="roas", measurable=False)
    assert goals.progress_fraction(g) is None
    assert goals.is_achieved(g) is False


# --------------------------------------------------------------------------
#  measure_goals — driven by the cycle
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_measure_goals_updates_and_achieves(monkeypatch):
    g_ongoing = _goal(metric="leads", current_value=20, target_value=100)
    g_hit = _goal(metric="website_traffic", current_value=0, target_value=500)
    monkeypatch.setattr(
        goals, "list_goals", AsyncMock(return_value=[g_ongoing, g_hit])
    )

    achieved = await goals.measure_goals(
        None, brand_id=uuid.uuid4(), metrics={"total_leads": 55, "total_views": 600}
    )
    assert g_ongoing.current_value == 55  # updated
    assert g_ongoing.status == "active"
    assert g_hit.current_value == 600
    assert g_hit.status == "achieved"  # target met
    assert achieved == 1


@pytest.mark.asyncio
async def test_measure_goals_ignores_unmeasured_metric(monkeypatch):
    g = _goal(metric="roas", measurable=False, current_value=0)
    monkeypatch.setattr(goals, "list_goals", AsyncMock(return_value=[g]))
    achieved = await goals.measure_goals(
        None, brand_id=uuid.uuid4(), metrics={"total_leads": 999}
    )
    assert g.current_value == 0  # untouched (no snapshot key)
    assert achieved == 0


# --------------------------------------------------------------------------
#  Context feed (Strategy / Planner / Decision)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_goals_context_empty_is_safe(monkeypatch):
    monkeypatch.setattr(goals, "list_goals", AsyncMock(return_value=[]))
    block = await goals.active_goals_context(None, brand_id=uuid.uuid4())
    assert "none set yet" in block


@pytest.mark.asyncio
async def test_active_goals_context_lists_progress(monkeypatch):
    g = _goal(baseline_value=20, current_value=60, target_value=100, title="Grow leads")
    monkeypatch.setattr(goals, "list_goals", AsyncMock(return_value=[g]))
    block = await goals.active_goals_context(None, brand_id=uuid.uuid4())
    assert "Grow leads" in block and "50%" in block
