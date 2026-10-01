"""Typed DTOs for the agent-action approval pipeline (Phase 4A).

Request bodies carry NO tenant/organization/brand/user id and NO approval state
— all authority is derived server-side from the authenticated session. The model
may propose only a tool name, its arguments, and human-readable reason/effect.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProposeActionRequest(BaseModel):
    """What the agent (or a client acting for it) may propose. ``extra='forbid'``
    blocks smuggled authority fields (approved, status, tenant_id, …)."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)
    expected_effect: str = Field(default="", max_length=2000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class ApprovalView(BaseModel):
    id: uuid.UUID
    tool_name: str
    operation_class: str
    status: str
    action_fingerprint: str
    autonomy_action_type: str | None = None
    policy_mode: str | None = None
    reason: str | None = None
    expected_effect: str | None = None
    requested_by_user_id: uuid.UUID
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    expires_at: datetime
    executed_at: datetime | None = None
    result: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    # Convenience flag for a UI: approval cleared the exact action.
    approval_required: bool = True


class ApprovalListResponse(BaseModel):
    items: list[ApprovalView] = Field(default_factory=list)


class ProposeActionResponse(BaseModel):
    """Proposing a consequential action NEVER executes it — it always pauses for a
    human decision. ``approval_required`` is always True in Phase 4A."""

    approval: ApprovalView
    approval_required: bool = True
    executed: bool = False
    message: str
