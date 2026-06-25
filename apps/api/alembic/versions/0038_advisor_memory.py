"""Advisor memory — persistent recommendations + task lifecycle

Revision ID: 0038_advisor_memory
Revises: 0037_render_asset_links
Create Date: 2026-06-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_advisor_memory"
down_revision: Union[str, None] = "0037_render_asset_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "advisor_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("record_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="not_started",
        ),
        sa.Column("impact_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impact_category", sa.String(length=16), nullable=True),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column(
            "data_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("source_surface", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "generator_hint",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("linked_asset_type", sa.String(length=32), nullable=True),
        sa.Column("linked_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "parent_recommendation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("outcome_summary", sa.Text(), nullable=True),
        sa.Column("repeat_rationale", sa.Text(), nullable=True),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "skipped_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_by_user_id",
            postgresql.UUID(as_uuid=True),
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
    op.create_index(
        "ix_advisor_recommendations_brand_status_created",
        "advisor_recommendations",
        ["brand_id", "status", "created_at"],
    )
    op.create_index(
        "ix_advisor_recommendations_brand_fingerprint",
        "advisor_recommendations",
        ["brand_id", "source_fingerprint"],
    )
    op.create_index(
        "ix_advisor_recommendations_brand_type_created",
        "advisor_recommendations",
        ["brand_id", "record_type", "created_at"],
    )

    op.create_table(
        "advisor_memory_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advisor_recommendations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
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
    )
    op.create_index(
        "ix_advisor_memory_events_recommendation_id",
        "advisor_memory_events",
        ["recommendation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_advisor_memory_events_recommendation_id", table_name="advisor_memory_events")
    op.drop_table("advisor_memory_events")
    op.drop_index("ix_advisor_recommendations_brand_type_created", table_name="advisor_recommendations")
    op.drop_index("ix_advisor_recommendations_brand_fingerprint", table_name="advisor_recommendations")
    op.drop_index("ix_advisor_recommendations_brand_status_created", table_name="advisor_recommendations")
    op.drop_table("advisor_recommendations")
