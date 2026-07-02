"""Module 9 — Autonomy Policy Layer tests (pure evaluation + integration)."""

from __future__ import annotations

from datetime import UTC, datetime

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
#  Orchestrator consults the policy (Module 8 × 9)
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

    # Policy granting full autonomy for campaign_launch → execute auto-eligible.
    stages2 = orch._assess_stages(st)

    async def auto_cfg(_s, *, brand_id):
        return AutonomyPolicyConfig(
            policies={"campaign_launch": ActionPolicy(mode="auto_always")}
        )

    monkeypatch.setattr(service, "get_or_default", auto_cfg)
    await orch._apply_autonomy_policy(None, tenant=_Tenant(), stages=stages2)
    ex2 = next(s for s in stages2 if s.key == "execute")
    assert ex2.auto_eligible is True and ex2.requires_approval is False
    assert ex2.policy_mode == "auto_always"


class _Tenant:
    brand_id = "brand-1"
    organization_id = "org-1"
    user_id = "u1"
