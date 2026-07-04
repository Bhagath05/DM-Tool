"""Phase 6.5 Slice 5 — AI Sales Assistant: crm_ai_insights.

One tenant-scoped table caching the evidence-contract insight for any CRM
subject (polymorphic subject_type/subject_id → reuse existing rows, no
duplication). Additive; no existing table touched.

Revision ID: 0065_crm_ai_insights
Revises: 0064_crm_email
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0065_crm_ai_insights"
down_revision: str | None = "0064_crm_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "crm_ai_insights",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", UUID, nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("evidence", JSONB, server_default="[]", nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("affected_records", JSONB, server_default="[]", nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("insufficient_evidence", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("generated_by_user_id", sa.String(255), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for col in ("brand_id", "subject_type", "subject_id", "kind", "insufficient_evidence", "expires_at"):
        op.create_index(f"ix_crm_ai_insights_{col}", "crm_ai_insights", [col])


def downgrade() -> None:
    op.drop_table("crm_ai_insights")
