"""rendered_visuals table

Revision ID: 0010_rendered_visuals
Revises: 0009_bundles
Create Date: 2026-05-23

Phase 4-A — one table, additive. Each row is one physical PNG sitting on
disk, generated from a visuals brief via the image-provider abstraction.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_rendered_visuals"
down_revision: Union[str, None] = "0009_bundles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rendered_visuals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("visual_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_image_id", sa.String(length=128), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(length=32),
            nullable=False,
            server_default="image/png",
        ),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "cost_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "latency_ms", sa.Integer(), nullable=False, server_default="0"
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
        sa.ForeignKeyConstraint(
            ["visual_id"], ["generated_visuals.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rendered_visuals_user_id", "rendered_visuals", ["user_id"]
    )
    op.create_index(
        "ix_rendered_visuals_visual_id", "rendered_visuals", ["visual_id"]
    )
    op.create_index(
        "ix_rendered_visuals_prompt_fp",
        "rendered_visuals",
        ["prompt_fingerprint"],
    )
    # Composite index for the daily-cap query (count by user in last 24h).
    op.create_index(
        "ix_rendered_visuals_user_created",
        "rendered_visuals",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rendered_visuals_user_created", table_name="rendered_visuals"
    )
    op.drop_index(
        "ix_rendered_visuals_prompt_fp", table_name="rendered_visuals"
    )
    op.drop_index(
        "ix_rendered_visuals_visual_id", table_name="rendered_visuals"
    )
    op.drop_index("ix_rendered_visuals_user_id", table_name="rendered_visuals")
    op.drop_table("rendered_visuals")
