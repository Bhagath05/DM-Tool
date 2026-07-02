"""Phase 3.9 — autonomy_policies table (Autonomy Policy Layer).

One row per brand governing what the AI may execute automatically. Purely
additive (a new table) — no impact on existing tables or data. Absence resolves
to the safe default (approve everything), so this migration changes no behaviour
until an admin configures a policy.

Revision ID: 0049_autonomy_policies
Revises: 0048_learning_insights
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_autonomy_policies"
down_revision: Union[str, None] = "0048_learning_insights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "autonomy_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "default_mode",
            sa.String(length=32),
            server_default="always_approve",
            nullable=False,
        ),
        sa.Column(
            "policies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "business_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "trusted", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_autonomy_policies_user_id", "autonomy_policies", ["user_id"]
    )
    op.create_index(
        "ix_autonomy_policies_organization_id",
        "autonomy_policies",
        ["organization_id"],
    )
    op.create_index(
        "ix_autonomy_policies_brand_id", "autonomy_policies", ["brand_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_autonomy_policies_brand_id", "autonomy_policies")
    op.drop_index("ix_autonomy_policies_organization_id", "autonomy_policies")
    op.drop_index("ix_autonomy_policies_user_id", "autonomy_policies")
    op.drop_table("autonomy_policies")
