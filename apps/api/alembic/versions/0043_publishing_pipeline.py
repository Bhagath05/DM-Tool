"""Publishing pipeline — content assets, calendar, publish events

Revision ID: 0043_publishing_pipeline
Revises: 0042_agent_reports
Create Date: 2026-06-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043_publishing_pipeline"
down_revision: Union[str, None] = "0042_agent_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_assets",
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
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advisor_recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("source_table", sa.String(length=32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "payload",
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
    )
    op.create_index("ix_content_assets_brand", "content_assets", ["brand_id"])
    op.create_index(
        "ix_content_assets_recommendation",
        "content_assets",
        ["recommendation_id"],
    )
    op.create_index(
        "ix_content_assets_source",
        "content_assets",
        ["source_table", "source_id"],
    )

    op.create_table(
        "scheduled_posts",
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
            "content_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advisor_recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "publish_status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("platform_post_id", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "social_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("social_assets.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index("ix_scheduled_posts_brand", "scheduled_posts", ["brand_id"])
    op.create_index(
        "ix_scheduled_posts_due",
        "scheduled_posts",
        ["publish_status", "scheduled_at"],
    )

    op.create_table(
        "publish_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scheduled_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scheduled_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "detail",
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
    )
    op.create_index(
        "ix_publish_events_scheduled_post",
        "publish_events",
        ["scheduled_post_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_publish_events_scheduled_post", table_name="publish_events")
    op.drop_table("publish_events")
    op.drop_index("ix_scheduled_posts_due", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_brand", table_name="scheduled_posts")
    op.drop_table("scheduled_posts")
    op.drop_index("ix_content_assets_source", table_name="content_assets")
    op.drop_index("ix_content_assets_recommendation", table_name="content_assets")
    op.drop_index("ix_content_assets_brand", table_name="content_assets")
    op.drop_table("content_assets")
