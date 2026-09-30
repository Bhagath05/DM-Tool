"""Agent runtime (Phase 2): conversational history.

Adds two normalized, tenant-scoped tables — ``agent_conversations`` and
``agent_messages`` — for the read-only Jarvis agent's conversation persistence.
Both carry organization_id + brand_id (TenantMixin) and receive the same dormant
org-scoped RLS policy as the other tenant tables (ENABLE/FORCE via
scripts/rls_activate.py). Purely additive.

Revision ID: 0076_agent_conversations
Revises: 0075_auth_email_suppression
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from aicmo.db import rls
from alembic import op

revision: str = "0076_agent_conversations"
down_revision: str | None = "0075_auth_email_suppression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=True)


def _tenant_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "organization_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            _UUID,
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", _UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_agent_conversations_status"),
    )
    op.create_index("ix_agent_conversations_organization_id", "agent_conversations", ["organization_id"])
    op.create_index("ix_agent_conversations_brand_id", "agent_conversations", ["brand_id"])
    op.create_index("ix_agent_conversations_brand_updated", "agent_conversations", ["brand_id", "updated_at"])

    op.create_table(
        "agent_messages",
        sa.Column("id", _UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column(
            "conversation_id",
            _UUID,
            sa.ForeignKey("agent_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("meta", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool', 'system')", name="ck_agent_messages_role"
        ),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_agent_messages_conversation_seq"),
    )
    op.create_index("ix_agent_messages_organization_id", "agent_messages", ["organization_id"])
    op.create_index("ix_agent_messages_brand_id", "agent_messages", ["brand_id"])
    op.create_index("ix_agent_messages_conversation_seq", "agent_messages", ["conversation_id", "seq"])

    # Dormant org-scoped RLS policies (same pattern as the other tenant tables).
    for table in ("agent_conversations", "agent_messages"):
        op.execute(rls.create_policy_sql(table))


def downgrade() -> None:
    for table in ("agent_messages", "agent_conversations"):
        op.execute(rls.drop_policy_sql(table))
    op.drop_index("ix_agent_messages_conversation_seq", table_name="agent_messages")
    op.drop_index("ix_agent_messages_brand_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_organization_id", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_conversations_brand_updated", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_brand_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_organization_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
