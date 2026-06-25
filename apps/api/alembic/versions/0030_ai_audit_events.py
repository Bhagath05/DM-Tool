"""AI generation audit trail — Phase S-AI-AUDIT

Revision ID: 0030_ai_audit_events
Revises: 0029_brand_profile
Create Date: 2026-06-10

Adds `ai_audit_events` — one row per AI generation call (success OR
failure), separate from the existing `audit_events` (admin mutations)
and `experiments` (learning-lab analytics).

Required columns (per Phase S deliverable):

  user_id, organization_id, brand_id, created_at,
  action_type, model_used, asset_id, generation_status

Plus operational columns the audit needs to be useful:

  error_class, duration_ms, request_id, prompt_token_count,
  completion_token_count, ip_address, metadata_json

CRITICAL — no generated content is stored. Captions, ad copy, image
URLs, hooks, anything the model produced is OFF the table. The audit
records THAT generation happened, by WHOM, WHEN, with WHICH model.

Indexes prioritise the three query shapes:
  1. "all activity by this user in the last 30d"
  2. "all activity in this org/brand in the last 30d"
  3. "all failures across the platform in the last 24h"

Rollback drops the table cleanly. Safe — nothing else FK's into it.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0030_ai_audit_events"
down_revision: Union[str, None] = "0029_brand_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Optional pointer to the generated row (no FK — asset tables vary).",
        ),
        sa.Column(
            "generation_status",
            sa.String(length=32),
            nullable=False,
            server_default="success",
            comment="success | failed | partial",
        ),
        sa.Column("error_class", sa.String(length=255), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("prompt_token_count", sa.Integer(), nullable=True),
        sa.Column("completion_token_count", sa.Integer(), nullable=True),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Non-content metadata only — never the generated text/image.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_ai_audit_org_created",
        "ai_audit_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_ai_audit_user_created",
        "ai_audit_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_audit_action_created",
        "ai_audit_events",
        ["action_type", "created_at"],
    )
    op.create_index(
        "ix_ai_audit_brand_created",
        "ai_audit_events",
        ["organization_id", "brand_id", "created_at"],
    )
    op.create_index(
        "ix_ai_audit_status_created",
        "ai_audit_events",
        ["generation_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_audit_status_created", table_name="ai_audit_events")
    op.drop_index("ix_ai_audit_brand_created", table_name="ai_audit_events")
    op.drop_index("ix_ai_audit_action_created", table_name="ai_audit_events")
    op.drop_index("ix_ai_audit_user_created", table_name="ai_audit_events")
    op.drop_index("ix_ai_audit_org_created", table_name="ai_audit_events")
    op.drop_table("ai_audit_events")
