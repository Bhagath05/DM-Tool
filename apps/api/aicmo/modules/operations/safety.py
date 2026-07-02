"""Phase 4.9 — Safety.

The single chokepoint every side-effecting action MUST pass before it runs. The
AI must NEVER automatically spend money, publish, delete assets, send emails, or
modify integrations unless the Autonomy Policy Layer + the platform master
switch permit it — this module enforces exactly that.

Today nothing in the operations loop executes those actions (it observes and
queues). When real execution wiring is added later, it goes through
`assert_action_permitted`, which fails CLOSED: any ambiguity → not permitted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

# The irreversible / money- / outbound-affecting actions that must never
# auto-run without explicit policy permission (the user's 4.9 list, mapped to
# autonomy action types).
SIDE_EFFECTING_ACTIONS: tuple[str, ...] = (
    "ad_spending",        # spend money
    "budget_change",      # spend money
    "campaign_launch",    # publish / launch
    "social_publishing",  # publish
    "email_sending",      # send emails
    "ad_creation",        # can incur spend on launch
    "crm_update",         # modify records
    "integration",        # modify integrations
)


class ActionNotPermitted(Exception):
    """Raised when a side-effecting action is attempted but policy/master switch
    do not permit automatic execution. Callers must fall back to human approval."""

    def __init__(self, action_type: str, reason: str) -> None:
        self.action_type = action_type
        self.reason = reason
        super().__init__(f"Action '{action_type}' not permitted to auto-run: {reason}")


def is_side_effecting(action_type: str) -> bool:
    return action_type in SIDE_EFFECTING_ACTIONS


async def assert_action_permitted(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    action_type: str,
    amount: float | None = None,
    now: datetime | None = None,
):
    """THE guard. Returns the PolicyDecision when auto-execution is permitted;
    raises ActionNotPermitted otherwise. Fails closed."""
    from aicmo.config import get_settings
    from aicmo.modules.autonomy import service as autonomy_service

    config = await autonomy_service.get_or_default(session, brand_id=brand_id)
    exec_enabled = get_settings().autonomy_execution_enabled
    decision = autonomy_service.evaluate_policy(
        config, action_type, amount=amount, now=now, execution_enabled=exec_enabled
    )
    if not decision.allow_auto:
        raise ActionNotPermitted(action_type, decision.reason)
    return decision


async def safety_status(session: AsyncSession, *, brand_id: uuid.UUID) -> dict:
    """The brand's current safety posture: the master switch + how each
    side-effecting action would resolve right now. Read-only."""
    from aicmo.config import get_settings
    from aicmo.modules.autonomy import service as autonomy_service

    config = await autonomy_service.get_or_default(session, brand_id=brand_id)
    exec_enabled = get_settings().autonomy_execution_enabled

    actions = []
    for action in SIDE_EFFECTING_ACTIONS:
        d = autonomy_service.evaluate_policy(
            config, action, execution_enabled=exec_enabled
        )
        actions.append({
            "action_type": action,
            "auto_eligible": d.allow_auto,
            "requires_approval": d.requires_approval,
            "policy_mode": d.mode,
        })
    any_auto = any(a["auto_eligible"] for a in actions)
    return {
        "execution_enabled": exec_enabled,
        "autonomy_level": config.autonomy_level,
        "all_side_effecting_gated": not any_auto,
        "actions": actions,
        "summary": (
            "Fully safe — no side-effecting action can auto-run; everything needs "
            "your approval."
            if not any_auto
            else "Some side-effecting actions can auto-run under your current policy."
        ),
    }
