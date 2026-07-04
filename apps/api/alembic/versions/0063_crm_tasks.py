"""Phase 6.5 Slice 3 — CRM tasks & calendar.

One tenant-scoped table `crm_tasks` with recurrence + calendar fields + nullable
links (SET NULL) to lead / contact / company / deal / campaign — reuse, no
duplicate records. Additive; no existing table touched.

Revision ID: 0063_crm_tasks
Revises: 0062_crm_entities
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0063_crm_tasks"
down_revision: str | None = "0062_crm_entities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "crm_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activity_type", sa.String(20), server_default="follow_up", nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("priority", sa.String(8), server_default="medium", nullable=False),
        sa.Column("owner_user_id", sa.String(255), nullable=True),
        sa.Column("assignee_user_id", sa.String(255), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("recurrence", JSONB, nullable=True),
        sa.Column("recurrence_parent_id", UUID, sa.ForeignKey("crm_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("calendar_event", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attachments", JSONB, server_default="[]", nullable=False),
        sa.Column("tags", JSONB, server_default="[]", nullable=False),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", UUID, sa.ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("ai_suggestion", JSONB, nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for col in ("brand_id", "status", "activity_type", "owner_user_id", "assignee_user_id",
                "due_at", "deal_id", "contact_id", "company_id", "lead_id", "campaign_id"):
        op.create_index(f"ix_crm_tasks_{col}", "crm_tasks", [col])


def downgrade() -> None:
    op.drop_table("crm_tasks")
