"""Module 9 — Autonomy Policy Layer tests (pure evaluation + integration)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aicmo.modules.autonomy import service
from aicmo.modules.autonomy.schemas import (
    ActionPolicy,
    AutonomyPolicyConfig,
    BusinessHours,
)

# 2026-07-06 is a Monday; 2026-07-04 is a Saturday.
_MON_10 = datetime(2026, 7, 6, 10, tzinfo=UTC)
_MON_20 = datetime(2026, 7, 6, 20, tzinfo=UTC)
_SAT_10 = datetime(2026, 7, 4, 10, tzinfo=UTC)


def _config(**over) -> AutonomyPolicyConfig:
    return AutonomyPolicyConfig(**over)


# --------------------------------------------------------------------------
#  Safe defaults
# --------------------------------------------------------------------------
def test_default_config_requires_approval_for_everything():
    cfg = _config()  # no policies → default_mode always_approve
    assert cfg.default_mode == "always_approve"
    assert cfg.configured is False
    d = service.evaluate_policy(cfg, "social_publishing")
    assert d.requires_approval is True and d.allow_auto is False


# --------------------------------------------------------------------------
#  Each mode
# --------------------------------------------------------------------------
def test_auto_always_allows_auto():
    cfg = _config(policies={"ai_recommendation": ActionPolicy(mode="auto_always")})
    d = service.evaluate_policy(cfg, "ai_recommendation")
    assert d.allow_auto is True and d.requires_approval is False


def test_never_requires_approval():
    cfg = _config(policies={"email_sending": ActionPolicy(mode="never")})
    d = service.evaluate_policy(cfg, "email_sending")
    assert d.requires_approval is True
    assert "never" in d.reason.lower()


def test_auto_below_threshold_boundaries():
    cfg = _config(
        policies={"ad_spending": ActionPolicy(mode="auto_below_threshold", threshold_amount=100)}
    )
    assert service.evaluate_policy(cfg, "ad_spending", amount=80).allow_auto is True
    assert service.evaluate_policy(cfg, "ad_spending", amount=100).allow_auto is True  # inclusive
    assert service.evaluate_policy(cfg, "ad_spending", amount=150).requires_approval is True


def test_auto_below_threshold_fails_safe_without_amount_or_threshold():
    # No amount to compare → approval.
    cfg = _config(
        policies={"ad_spending": ActionPolicy(mode="auto_below_threshold", threshold_amount=100)}
    )
    assert service.evaluate_policy(cfg, "ad_spending", amount=None).requires_approval is True
    # No threshold set → approval.
    cfg2 = _config(policies={"ad_spending": ActionPolicy(mode="auto_below_threshold")})
    assert service.evaluate_policy(cfg2, "ad_spending", amount=10).requires_approval is True


def test_auto_business_hours_in_and_out():
    cfg = _config(
        policies={"social_publishing": ActionPolicy(mode="auto_business_hours")},
        business_hours=BusinessHours(
            enabled=True, start_hour=9, end_hour=18, timezone="UTC", days=[0, 1, 2, 3, 4]
        ),
    )
    assert service.evaluate_policy(cfg, "social_publishing", now=_MON_10).allow_auto is True
    assert service.evaluate_policy(cfg, "social_publishing", now=_MON_20).requires_approval is True
    # Weekend excluded.
    assert service.evaluate_policy(cfg, "social_publishing", now=_SAT_10).requires_approval is True


def test_auto_business_hours_disabled_is_safe():
    cfg = _config(
        policies={"social_publishing": ActionPolicy(mode="auto_business_hours")},
        business_hours=BusinessHours(enabled=False),
    )
    assert service.evaluate_policy(cfg, "social_publishing", now=_MON_10).requires_approval is True


def test_auto_business_hours_bad_timezone_fails_safe():
    cfg = _config(
        policies={"social_publishing": ActionPolicy(mode="auto_business_hours")},
        business_hours=BusinessHours(enabled=True, timezone="Not/AZone", days=[0]),
    )
    assert service.evaluate_policy(cfg, "social_publishing", now=_MON_10).requires_approval is True


def test_auto_if_trusted():
    cfg_untrusted = _config(
        policies={"campaign_launch": ActionPolicy(mode="auto_if_trusted")}, trusted=False
    )
    assert service.evaluate_policy(cfg_untrusted, "campaign_launch").requires_approval is True
    cfg_trusted = _config(
        policies={"campaign_launch": ActionPolicy(mode="auto_if_trusted")}, trusted=True
    )
    assert service.evaluate_policy(cfg_trusted, "campaign_launch").allow_auto is True


def test_unconfigured_action_uses_default_mode():
    cfg = _config(default_mode="auto_always")
    # crm_update isn't in policies → inherits default.
    assert service.evaluate_policy(cfg, "crm_update").allow_auto is True


# --------------------------------------------------------------------------
#  Catalog
# --------------------------------------------------------------------------
def test_catalog_lists_all_actions_and_modes():
    cat = service.catalog()
    keys = {e.key for e in cat.action_types}
    assert {"social_publishing", "ad_spending", "ai_decision", "crm_update"} <= keys
    modes = {e.key for e in cat.modes}
    assert {"always_approve", "auto_always", "auto_below_threshold", "never"} <= modes


# --------------------------------------------------------------------------
#  Orchestrator consults the policy (Module 8 x 9)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_applies_policy_to_execute_stage(monkeypatch):
    from aicmo.modules.orchestrator import service as orch
    from aicmo.modules.orchestrator.service import _State

    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    st.has_strategy = True
    stages = orch._assess_stages(st)

    # Default policy → execute stays approval-gated.
    async def default_cfg(_s, *, brand_id):
        return AutonomyPolicyConfig()

    monkeypatch.setattr(service, "get_or_default", default_cfg)
    await orch._apply_autonomy_policy(None, tenant=_Tenant(), stages=list(stages))
    ex = next(s for s in stages if s.key == "execute")
    assert ex.requires_approval is True and ex.auto_eligible is False

    # Full autonomy for campaign_launch, but the platform master switch is OFF
    # (default) → the orchestrator STILL gates it. Safety holds.
    stages_off = orch._assess_stages(st)

    async def auto_cfg(_s, *, brand_id):
        return AutonomyPolicyConfig(
            policies={"campaign_launch": ActionPolicy(mode="auto_always")}
        )

    monkeypatch.setattr(service, "get_or_default", auto_cfg)
    await orch._apply_autonomy_policy(None, tenant=_Tenant(), stages=stages_off)
    ex_off = next(s for s in stages_off if s.key == "execute")
    assert ex_off.requires_approval is True and ex_off.auto_eligible is False

    # Same policy, but the master switch ON → execute becomes auto-eligible.
    import aicmo.config as config_mod

    monkeypatch.setattr(
        config_mod,
        "get_settings",
        lambda: SimpleNamespace(autonomy_execution_enabled=True),
    )
    stages_on = orch._assess_stages(st)
    await orch._apply_autonomy_policy(None, tenant=_Tenant(), stages=stages_on)
    ex_on = next(s for s in stages_on if s.key == "execute")
    assert ex_on.auto_eligible is True and ex_on.requires_approval is False
    assert ex_on.policy_mode == "auto_always"


class _Tenant:
    brand_id = "brand-1"
    organization_id = "org-1"
    user_id = "u1"


# --------------------------------------------------------------------------
#  Module 10 — master switch + progressive levels
# --------------------------------------------------------------------------
def test_master_switch_downgrades_auto_to_approval():
    cfg = _config(policies={"ai_recommendation": ActionPolicy(mode="auto_always")})
    # Master ON → auto allowed.
    on = service.evaluate_policy(cfg, "ai_recommendation", execution_enabled=True)
    assert on.allow_auto is True
    # Master OFF → the same policy is downgraded to requiring approval.
    off = service.evaluate_policy(cfg, "ai_recommendation", execution_enabled=False)
    assert off.allow_auto is False and off.requires_approval is True
    assert "master switch" in off.reason


def _config_for_level(level: str) -> AutonomyPolicyConfig:
    from aicmo.modules.autonomy import levels as levels_mod

    dm, preset = levels_mod.preset_for(level)
    return AutonomyPolicyConfig(
        default_mode=dm,  # type: ignore[arg-type]
        policies={a: ActionPolicy(mode=m) for a, m in preset.items()},  # type: ignore[arg-type]
    )


def test_manual_level_keeps_everything_approval():
    cfg = _config_for_level("manual")
    for action in ("content_generation", "social_publishing", "ad_spending"):
        assert service.evaluate_policy(cfg, action, execution_enabled=True).requires_approval


def test_assisted_level_automates_drafting_not_publishing():
    cfg = _config_for_level("assisted")
    assert service.evaluate_policy(cfg, "content_generation", execution_enabled=True).allow_auto
    assert service.evaluate_policy(cfg, "ai_decision", execution_enabled=True).allow_auto
    # Publishing/spending still require approval.
    assert service.evaluate_policy(cfg, "social_publishing", execution_enabled=True).requires_approval
    assert service.evaluate_policy(cfg, "ad_spending", execution_enabled=True).requires_approval


def test_full_level_automates_all_but_master_switch_still_gates():
    cfg = _config_for_level("full")
    # Master ON → everything auto.
    assert service.evaluate_policy(cfg, "ad_spending", execution_enabled=True).allow_auto
    # Master OFF → nothing auto-runs even at 'full'.
    assert service.evaluate_policy(cfg, "ad_spending", execution_enabled=False).requires_approval


def test_levels_catalog_is_ordered_and_complete():
    from aicmo.modules.autonomy import levels as levels_mod

    cat = levels_mod.catalog()
    keys = [c["key"] for c in cat]
    assert keys == ["manual", "assisted", "scheduled", "supervised", "full"]
    assert all(cat[i]["order"] <= cat[i + 1]["order"] for i in range(len(cat) - 1))


def test_unknown_level_falls_back_to_manual():
    from aicmo.modules.autonomy import levels as levels_mod

    assert levels_mod.preset_for("bogus") == levels_mod.preset_for("manual")
    assert levels_mod.is_level("bogus") is False
