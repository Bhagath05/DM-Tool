"""Agent consequential-action approval record (Phase 4A).

One row = one proposed consequential action awaiting (or past) a human decision.
It stores the SERVER-VALIDATED action (tool + validated input), the action
fingerprint it is bound to, the autonomy-policy snapshot, the explicit status,
the human actor who decided, a short TTL, and the structured execution result.

The LLM-proposed ``reason`` / ``expected_effect`` are stored as DATA for display
only — they never influence authorization, state, or execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin
from aicmo.modules.agent_actions.enums import ApprovalStatus

_STATUS_IN = ", ".join(f"'{s.value}'" for s in ApprovalStatus)


class AgentActionApproval(Base, TenantMixin, TimestampMixin):
    """A human-approval gate for one agent-proposed consequential action."""

    __tablename__ = "agent_action_approvals"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_IN})", name="ck_agent_action_status"),
        CheckConstraint(
            "operation_class = 'consequential'", name="ck_agent_action_operation_class"
        ),
        Index("ix_agent_action_brand_status", "brand_id", "status"),
        Index("ix_agent_action_fingerprint", "action_fingerprint"),
        Index("ix_agent_action_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who proposed (the authenticated user whose session ran the agent).
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_class: Mapped[str] = mapped_column(String(16), nullable=False)
    # The SERVER-VALIDATED tool input (never raw LLM JSON).
    action_input: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Hash over the canonical validated action — the exact-action binding.
    action_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Execution idempotency key derived from the fingerprint.
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Autonomy-policy snapshot at proposal time (recorded, never auto-approves).
    autonomy_action_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    policy_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # LLM-proposed, DISPLAY ONLY. Never authoritative.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_effect: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ApprovalStatus.PENDING.value,
        server_default=ApprovalStatus.PENDING.value, index=True,
    )

    # The human who decided (approve/reject) — the real actor, server-derived.
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Structured, schema-validated result summary (never raw external text).
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
