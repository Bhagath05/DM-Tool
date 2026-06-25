"""lead capture engine

Revision ID: 0007_lead_capture
Revises: 0006_campaign_plans
Create Date: 2026-05-22

Adds:
- landing_pages
- leads (with composite indexes for inbox queries)
- rate_limit_buckets (postgres-backed rate limiter)
- landing_page_id attribution columns on existing asset tables
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_lead_capture"
down_revision: Union[str, None] = "0006_campaign_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- landing_pages ----------
    op.create_table(
        "landing_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "business_profile_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("preview_token", sa.String(length=64), nullable=False),
        sa.Column(
            "content", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("redirect_url", sa.String(length=512), nullable=True),
        sa.Column(
            "view_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "submission_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
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
            ["business_profile_id"],
            ["business_profiles.id"],
            ondelete="CASCADE",
            name="fk_landing_pages_business_profile",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_landing_pages_slug"),
    )
    op.create_index("ix_landing_pages_user_id", "landing_pages", ["user_id"])
    op.create_index(
        "ix_landing_pages_business_profile_id",
        "landing_pages",
        ["business_profile_id"],
    )
    op.create_index("ix_landing_pages_slug", "landing_pages", ["slug"])

    # ---------- leads ----------
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "business_profile_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "extra_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "landing_page_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("source_asset_type", sa.String(length=32), nullable=True),
        sa.Column("source_asset_id", sa.String(length=64), nullable=True),
        sa.Column("utm_source", sa.String(length=128), nullable=True),
        sa.Column("utm_medium", sa.String(length=128), nullable=True),
        sa.Column("utm_campaign", sa.String(length=128), nullable=True),
        sa.Column("utm_term", sa.String(length=128), nullable=True),
        sa.Column("utm_content", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("referrer", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'new'"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["business_profile_id"],
            ["business_profiles.id"],
            ondelete="CASCADE",
            name="fk_leads_business_profile",
        ),
        sa.ForeignKeyConstraint(
            ["landing_page_id"],
            ["landing_pages.id"],
            ondelete="SET NULL",
            name="fk_leads_landing_page",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_user_id", "leads", ["user_id"])
    op.create_index(
        "ix_leads_business_profile_id", "leads", ["business_profile_id"]
    )
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_landing_page_id", "leads", ["landing_page_id"])
    op.create_index("ix_leads_user_created", "leads", ["user_id", "created_at"])
    op.create_index("ix_leads_user_status", "leads", ["user_id", "status"])

    # ---------- rate_limit_buckets ----------
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "window_start", name="uq_rl_key_window"),
    )
    op.create_index("ix_rl_key", "rate_limit_buckets", ["key"])
    op.create_index("ix_rl_window", "rate_limit_buckets", ["window_start"])

    # ---------- attribution columns on existing tables ----------
    for table in (
        "generated_content",
        "generated_ads",
        "generated_visuals",
        "campaign_plans",
    ):
        op.add_column(
            table,
            sa.Column(
                "landing_page_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_landing_page",
            table,
            "landing_pages",
            ["landing_page_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"ix_{table}_landing_page_id", table, ["landing_page_id"]
        )


def downgrade() -> None:
    for table in (
        "generated_content",
        "generated_ads",
        "generated_visuals",
        "campaign_plans",
    ):
        op.drop_index(f"ix_{table}_landing_page_id", table_name=table)
        op.drop_constraint(f"fk_{table}_landing_page", table, type_="foreignkey")
        op.drop_column(table, "landing_page_id")

    op.drop_index("ix_rl_window", table_name="rate_limit_buckets")
    op.drop_index("ix_rl_key", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")

    op.drop_index("ix_leads_user_status", table_name="leads")
    op.drop_index("ix_leads_user_created", table_name="leads")
    op.drop_index("ix_leads_landing_page_id", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_business_profile_id", table_name="leads")
    op.drop_index("ix_leads_user_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_landing_pages_slug", table_name="landing_pages")
    op.drop_index(
        "ix_landing_pages_business_profile_id", table_name="landing_pages"
    )
    op.drop_index("ix_landing_pages_user_id", table_name="landing_pages")
    op.drop_table("landing_pages")
