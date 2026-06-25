"""social intelligence layer

Revision ID: 0011_social_intelligence
Revises: 0010_rendered_visuals
Create Date: 2026-05-26

Phase 1 of the Social Intelligence Layer — read-only foundation. Five
tables, no auto-posting infrastructure here by design.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_social_intelligence"
down_revision: Union[str, None] = "0010_rendered_visuals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # social_connections
    op.create_table(
        "social_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="oauth",
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), nullable=True
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "platform", name="uq_social_connection_user_platform"
        ),
    )
    op.create_index(
        "ix_social_connections_user_id", "social_connections", ["user_id"]
    )
    op.create_index(
        "ix_social_connections_platform", "social_connections", ["platform"]
    )

    # social_assets
    op.create_table(
        "social_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "connection_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_post_id", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("permalink", sa.Text(), nullable=True),
        sa.Column(
            "hashtags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
            ["connection_id"],
            ["social_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "platform",
            "platform_post_id",
            name="uq_social_asset_post",
        ),
    )
    op.create_index(
        "ix_social_assets_user_id", "social_assets", ["user_id"]
    )
    op.create_index(
        "ix_social_assets_platform", "social_assets", ["platform"]
    )
    op.create_index(
        "ix_social_assets_connection_id",
        "social_assets",
        ["connection_id"],
    )
    op.create_index(
        "ix_social_assets_asset_type", "social_assets", ["asset_type"]
    )
    op.create_index(
        "ix_social_assets_posted_at", "social_assets", ["posted_at"]
    )

    # performance_signals
    op.create_table(
        "performance_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "asset_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "impressions", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "comments_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "shares", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "engagement_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "watch_time_seconds",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False
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
            ["asset_id"], ["social_assets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performance_signals_asset_id",
        "performance_signals",
        ["asset_id"],
    )
    op.create_index(
        "ix_performance_signals_captured_at",
        "performance_signals",
        ["captured_at"],
    )

    # audience_patterns
    op.create_table(
        "audience_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("pattern_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.5",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audience_patterns_user_id",
        "audience_patterns",
        ["user_id"],
    )
    op.create_index(
        "ix_audience_patterns_platform",
        "audience_patterns",
        ["platform"],
    )

    # winning_patterns
    op.create_table(
        "winning_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("hook_pattern", sa.Text(), nullable=True),
        sa.Column("visual_pattern", sa.Text(), nullable=True),
        sa.Column("caption_pattern", sa.Text(), nullable=True),
        sa.Column("cta_pattern", sa.Text(), nullable=True),
        sa.Column("format_pattern", sa.Text(), nullable=True),
        sa.Column("posting_time_pattern", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "performance_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "source_asset_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_winning_patterns_user_id", "winning_patterns", ["user_id"]
    )
    op.create_index(
        "ix_winning_patterns_platform", "winning_patterns", ["platform"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_winning_patterns_platform", table_name="winning_patterns"
    )
    op.drop_index(
        "ix_winning_patterns_user_id", table_name="winning_patterns"
    )
    op.drop_table("winning_patterns")
    op.drop_index(
        "ix_audience_patterns_platform", table_name="audience_patterns"
    )
    op.drop_index(
        "ix_audience_patterns_user_id", table_name="audience_patterns"
    )
    op.drop_table("audience_patterns")
    op.drop_index(
        "ix_performance_signals_captured_at",
        table_name="performance_signals",
    )
    op.drop_index(
        "ix_performance_signals_asset_id",
        table_name="performance_signals",
    )
    op.drop_table("performance_signals")
    op.drop_index(
        "ix_social_assets_posted_at", table_name="social_assets"
    )
    op.drop_index(
        "ix_social_assets_asset_type", table_name="social_assets"
    )
    op.drop_index(
        "ix_social_assets_connection_id", table_name="social_assets"
    )
    op.drop_index(
        "ix_social_assets_platform", table_name="social_assets"
    )
    op.drop_index(
        "ix_social_assets_user_id", table_name="social_assets"
    )
    op.drop_table("social_assets")
    op.drop_index(
        "ix_social_connections_platform",
        table_name="social_connections",
    )
    op.drop_index(
        "ix_social_connections_user_id",
        table_name="social_connections",
    )
    op.drop_table("social_connections")
