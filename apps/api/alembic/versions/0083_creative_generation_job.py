"""CS-1 creative generation jobs.

Existing creative tables store projects, assets, and cost rows. They do not
store one request that can succeed on one model and fail on another. This
table is that job record. Tokens and provider payloads are not stored.

Revision ID: 0083_creative_generation_job
Revises: 0082_business_profiles_economics
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0083_creative_generation_job"
down_revision: str | None = "0082_business_profiles_economics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creative_generation_job",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("params", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("results", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_creative_generation_job_brand", "creative_generation_job", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_creative_generation_job_brand", table_name="creative_generation_job")
    op.drop_table("creative_generation_job")
