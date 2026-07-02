"""Phase 4.6 — Trigger → Decision → Action pipeline tests (gated; mocked engines)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.operations import pipeline


class _FakeSession:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


def _decision(**over):
    base = dict(
        decision="Shift to Instagram reels this week",
        reasoning="Reels convert best",
        recommended_action="Publish 3 reels",
        urgency="this_week",
        business_objective="Get more leads",
        affected_channels=["instagram"],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _settings(enabled=True):
    return SimpleNamespace(
        operations_pipeline_enabled=enabled,
        operations_decision_cooldown_seconds=21600,
        operations_learning_cooldown_seconds=86400,
    )


def test_action_type_mapping_from_channels():
    assert pipeline._action_type_for(["email"]) == ("email", "email_sending")
    assert pipeline._action_type_for(["facebook ads"]) == ("ad", "ad_creation")
    assert pipeline._action_type_for(["instagram"]) == ("campaign_update", "campaign_creation")


@pytest.mark.asyncio
async def test_pipeline_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: _settings(enabled=False))
    out = await pipeline.run_reasoning(
        _FakeSession(), organization_id=uuid.uuid4(), brand_id=uuid.uuid4()
    )
    assert out["enabled"] is False
    assert out["decisions"] == 0 and out["learning_ran"] is False


@pytest.mark.asyncio
async def test_pipeline_runs_decisions_into_work_when_events_open(monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: _settings(enabled=True))
    ev = SimpleNamespace(status="new")
    monkeypatch.setattr(pipeline, "_open_high_sev_events", AsyncMock(return_value=[ev]))
    monkeypatch.setattr(pipeline, "_cooldown_elapsed", AsyncMock(return_value=True))

    report = SimpleNamespace(decisions=[_decision(), _decision(decision="Start an email nurture", affected_channels=["email"])])
    monkeypatch.setattr(
        "aicmo.modules.decision_engine.service.decide",
        AsyncMock(return_value=SimpleNamespace(report=report)),
    )
    persist = AsyncMock(return_value=2)
    monkeypatch.setattr("aicmo.modules.operations.scheduler.persist_drafts", persist)
    synth = AsyncMock()
    monkeypatch.setattr("aicmo.modules.learning.synthesis.synthesize", synth)

    session = _FakeSession()
    out = await pipeline.run_reasoning(
        session, organization_id=uuid.uuid4(), brand_id=uuid.uuid4()
    )

    assert out["decisions"] == 2
    assert out["work_from_decisions"] == 2
    assert out["learning_ran"] is True
    assert ev.status == "acknowledged"  # triggering event marked processed
    # decision drafts had distinct dedupe hints (different decision text)
    drafts = persist.await_args.kwargs["drafts"]
    assert len({d.dedupe_hint for d in drafts}) == 2


@pytest.mark.asyncio
async def test_pipeline_skips_decisions_when_no_open_events(monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(pipeline, "_open_high_sev_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_cooldown_elapsed", AsyncMock(return_value=True))
    decide = AsyncMock()
    monkeypatch.setattr("aicmo.modules.decision_engine.service.decide", decide)
    monkeypatch.setattr("aicmo.modules.learning.synthesis.synthesize", AsyncMock())

    out = await pipeline.run_reasoning(
        _FakeSession(), organization_id=uuid.uuid4(), brand_id=uuid.uuid4()
    )
    assert out["decisions"] == 0
    decide.assert_not_awaited()  # no events → Decision Engine not run (cost saved)
