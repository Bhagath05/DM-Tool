"""Agent consequential-action approvals (Phase 4A).

Adds ``agent_action_approvals`` — the human-approval gate for agent-proposed
consequential tool calls. Stores the server-validated action (tool + input), the
exact-action fingerprint it binds to, the autonomy-policy snapshot, the explicit
status, the human decider, a short TTL, and the structured execution result.
Tenant-scoped (organization_id + brand_id) with the same dormant org-scoped RLS
policy as the other tenant tables. Purely additive.

Revision ID: 0078_agent_action_approvals
Revises: 0077_belief_memory
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from aicmo.db import rls
from alembic import op

revision: str = "0078_agent_action_approvals"
down_revision: str | None = "0077_belief_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=True)

_STATUS_IN = "'pending', 'approved', 'rejected', 'expired', 'executed', 'failed'"


def upgrade() -> None:
    op.create_table(
        "agent_action_approvals",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "organization_id", _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "brand_id", _UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("requested_by_user_id", _UUID, nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("operation_class", sa.String(16), nullable=False),
        sa.Column("action_input", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("action_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("autonomy_action_type", sa.String(48), nullable=True),
        sa.Column("policy_mode", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expected_effect", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("decided_by_user_id", _UUID, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN ({_STATUS_IN})", name="ck_agent_action_status"),
        sa.CheckConstraint("operation_class = 'consequential'", name="ck_agent_action_operation_class"),
    )
    op.create_index("ix_agent_action_approvals_organization_id", "agent_action_approvals", ["organization_id"])
    op.create_index("ix_agent_action_brand_status", "agent_action_approvals", ["brand_id", "status"])
    op.create_index("ix_agent_action_fingerprint", "agent_action_approvals", ["action_fingerprint"])
    op.create_index("ix_agent_action_expires", "agent_action_approvals", ["expires_at"])

    op.execute(rls.create_policy_sql("agent_action_approvals"))


def downgrade() -> None:
    op.execute(rls.drop_policy_sql("agent_action_approvals"))
    op.drop_index("ix_agent_action_expires", table_name="agent_action_approvals")
    op.drop_index("ix_agent_action_fingerprint", table_name="agent_action_approvals")
    op.drop_index("ix_agent_action_brand_status", table_name="agent_action_approvals")
    op.drop_index("ix_agent_action_approvals_organization_id", table_name="agent_action_approvals")
    op.drop_table("agent_action_approvals")
