"""Phase 6.2B — enterprise content ops: versions, folders, comments, review.

4 new tenant-scoped tables + 2 additive columns on generated_content
(review_status, folder_id). Additive throughout — no rewrite, no backfill.

Revision ID: 0058_content_ops
Revises: 0057_content_asset_links
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058_content_ops"
down_revision: Union[str, None] = "0057_content_asset_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _tenant_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            UUID,
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=True,
        ),
    ]


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # content_folders (created first — generated_content.folder_id references it).
    op.create_table(
        "content_folders",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="folder", nullable=False),
        sa.Column("parent_id", UUID, sa.ForeignKey("content_folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=False),
        *_ts_cols(),
    )
    op.create_index("ix_content_folders_brand_id", "content_folders", ["brand_id"])
    op.create_index("ix_content_folders_parent_id", "content_folders", ["parent_id"])

    op.create_table(
        "content_versions",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("content_id", UUID, sa.ForeignKey("generated_content.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("output", JSONB, nullable=False),
        sa.Column("strategy", JSONB, server_default="{}", nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("edit_source", sa.String(length=16), server_default="ai", nullable=False),
        sa.Column("author_user_id", sa.String(length=255), nullable=False),
        *_ts_cols(),
    )
    op.create_index("ix_content_versions_content_id", "content_versions", ["content_id"])
    op.create_index("ix_content_versions_brand_id", "content_versions", ["brand_id"])

    op.create_table(
        "content_comments",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("content_id", UUID, sa.ForeignKey("generated_content.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", UUID, sa.ForeignKey("content_comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("author_user_id", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions", JSONB, server_default="[]", nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=255), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_content_comments_content_id", "content_comments", ["content_id"])
    op.create_index("ix_content_comments_parent_id", "content_comments", ["parent_id"])
    op.create_index("ix_content_comments_resolved", "content_comments", ["resolved"])

    op.create_table(
        "content_review_events",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("content_id", UUID, sa.ForeignKey("generated_content.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.String(length=255), nullable=False),
        *_ts_cols(),
    )
    op.create_index("ix_content_review_events_content_id", "content_review_events", ["content_id"])

    # generated_content additions.
    op.add_column(
        "generated_content",
        sa.Column("review_status", sa.String(length=24), server_default="draft", nullable=False),
    )
    op.add_column(
        "generated_content",
        sa.Column("folder_id", UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_generated_content_folder_id", "generated_content", "content_folders",
        ["folder_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_generated_content_review_status", "generated_content", ["review_status"])
    op.create_index("ix_generated_content_folder_id", "generated_content", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_generated_content_folder_id", "generated_content")
    op.drop_index("ix_generated_content_review_status", "generated_content")
    op.drop_constraint("fk_generated_content_folder_id", "generated_content", type_="foreignkey")
    op.drop_column("generated_content", "folder_id")
    op.drop_column("generated_content", "review_status")
    op.drop_table("content_review_events")
    op.drop_table("content_comments")
    op.drop_table("content_versions")
    op.drop_table("content_folders")
