"""Module 8 — Agent Orchestrator schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Where a stage sits. `not_started` (never done, no prereqs to do it yet handled
# by blocked), `ready` (do it now — the recommended action), `blocked` (a prior
# stage must happen first), `stale` (done but outdated — refresh), `done` (fresh),
# `needs_approval` (an action is queued for the human to approve).
StageStatus = Literal[
    "not_started", "ready", "blocked", "stale", "done", "needs_approval"
]

StageKey = Literal[
    "understand", "strategize", "plan", "decide", "execute", "learn", "review"
]


class LifecycleStage(BaseModel):
    key: StageKey
    label: str
    status: StageStatus
    reason: str = Field(description="Plain-language why this stage is in this status.")
    action: str | None = Field(
        default=None, description="The next step for this stage (a human triggers it)."
    )
    link: str = Field(description="Where to go to act on this stage.")
    requires_approval: bool = Field(
        default=False,
        description="True when acting here must be human-approved (per the autonomy policy).",
    )
    # Autonomy Policy Layer (Module 9) annotations — what the policy permits.
    auto_eligible: bool = Field(
        default=False,
        description="True when the autonomy policy would let this run automatically now.",
    )
    policy_mode: str | None = Field(
        default=None, description="The policy mode governing this action, if any."
    )
    blocked_by: StageKey | None = None


class NextAction(BaseModel):
    """The single highest-priority next step across the whole lifecycle."""

    stage: StageKey
    action: str
    why: str
    link: str
    requires_approval: bool
    auto_eligible: bool = False


class OrchestratorPlan(BaseModel):
    summary: str = Field(description="One plain line: the AI employee's next move and why.")
    current_stage: StageKey
    next_action: NextAction | None = Field(
        default=None, description="None only when everything is done + fresh."
    )
    stages: list[LifecycleStage]
    blocked_on: StageKey | None = None
    pending_approvals: list[str] = Field(
        default_factory=list,
        description="Actions already queued that await the human's approval.",
    )
    autonomy_note: str = Field(
        default=(
            "Nothing here runs automatically. Every step is a recommendation you "
            "approve and trigger — the AI plans and drafts; you decide."
        )
    )
    generated_at: str
