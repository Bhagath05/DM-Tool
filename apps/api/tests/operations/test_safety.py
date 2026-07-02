"""Phase 4.9 — Safety: prove no side-effecting action can auto-run by default."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aicmo.modules.autonomy.schemas import ActionPolicy, AutonomyPolicyConfig
from aicmo.modules.operations import safety


def _patch(monkeypatch, *, config, execution_enabled):
    monkeypatch.setattr(
        "aicmo.modules.autonomy.service.get_or_default",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(autonomy_execution_enabled=execution_enabled),
    )


# --------------------------------------------------------------------------
#  THE core invariant
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_side_effecting_action_auto_runs_by_default(monkeypatch):
    # Safe defaults: unconfigured policy + master switch OFF.
    _patch(monkeypatch, config=AutonomyPolicyConfig(), execution_enabled=False)
    for action in safety.SIDE_EFFECTING_ACTIONS:
        with pytest.raises(safety.ActionNotPermitted):
            await safety.assert_action_permitted(
                None, brand_id=uuid.uuid4(), action_type=action, amount=999999
            )


@pytest.mark.asyncio
async def test_master_switch_off_blocks_even_full_autonomy(monkeypatch):
    # Even a brand set to auto_always for spending — master OFF still blocks it.
    cfg = AutonomyPolicyConfig(
        default_mode="auto_always",
        policies={"ad_spending": ActionPolicy(mode="auto_always")},
    )
    _patch(monkeypatch, config=cfg, execution_enabled=False)
    with pytest.raises(safety.ActionNotPermitted):
        await safety.assert_action_permitted(
            None, brand_id=uuid.uuid4(), action_type="ad_spending", amount=10
        )


@pytest.mark.asyncio
async def test_permitted_only_when_policy_and_master_allow(monkeypatch):
    cfg = AutonomyPolicyConfig(
        policies={"social_publishing": ActionPolicy(mode="auto_always")}
    )
    _patch(monkeypatch, config=cfg, execution_enabled=True)
    decision = await safety.assert_action_permitted(
        None, brand_id=uuid.uuid4(), action_type="social_publishing"
    )
    assert decision.allow_auto is True  # no exception, explicitly permitted


# --------------------------------------------------------------------------
#  Coverage of the user's 4.9 list
# --------------------------------------------------------------------------
def test_side_effecting_list_covers_spend_publish_email_integrations():
    s = set(safety.SIDE_EFFECTING_ACTIONS)
    assert {"ad_spending", "budget_change"} <= s          # spend money
    assert {"social_publishing", "campaign_launch"} <= s  # publish
    assert "email_sending" in s                           # send emails
    assert "integration" in s                             # modify integrations


# --------------------------------------------------------------------------
#  Safety status posture
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_safety_status_reports_fully_safe_by_default(monkeypatch):
    _patch(monkeypatch, config=AutonomyPolicyConfig(), execution_enabled=False)
    status = await safety.safety_status(None, brand_id=uuid.uuid4())
    assert status["execution_enabled"] is False
    assert status["all_side_effecting_gated"] is True
    assert all(a["requires_approval"] for a in status["actions"])
    assert "Fully safe" in status["summary"]
