"""Phase 6.5 Slice 4 — CRM email platform.

7 tenant-scoped tables: templates (+ folders + immutable version history),
sequences (+ steps), enrollments, and the email record (tracking + provider +
CRM links). Additive; no existing table touched. Emails link (SET NULL) to
lead/contact/company/deal/campaign and to the crm_activities timeline row.

Revision ID: 0064_crm_email
Revises: 0063_crm_tasks
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0064_crm_email"
down_revision: str | None = "0063_crm_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _tenant() -> list[sa.Column]:
    return [
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
    ]


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "crm_email_folders",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parent_id", UUID, sa.ForeignKey("crm_email_folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        *_ts(),
    )
    op.create_index("ix_crm_email_folders_brand_id", "crm_email_folders", ["brand_id"])

    op.create_table(
        "crm_email_templates",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(24), server_default="custom", nullable=False),
        sa.Column("subject", sa.String(400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", JSONB, server_default="[]", nullable=False),
        sa.Column("folder_id", UUID, sa.ForeignKey("crm_email_folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        *_ts(),
    )
    for col in ("brand_id", "name", "category", "folder_id", "is_active"):
        op.create_index(f"ix_crm_email_templates_{col}", "crm_email_templates", [col])

    op.create_table(
        "crm_email_template_versions",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("template_id", UUID, sa.ForeignKey("crm_email_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", JSONB, server_default="[]", nullable=False),
        sa.Column("edit_summary", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_email_template_versions_template_id", "crm_email_template_versions", ["template_id"])

    op.create_table(
        "crm_email_sequences",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        *_ts(),
    )
    op.create_index("ix_crm_email_sequences_brand_id", "crm_email_sequences", ["brand_id"])
    op.create_index("ix_crm_email_sequences_status", "crm_email_sequences", ["status"])

    op.create_table(
        "crm_email_sequence_steps",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("sequence_id", UUID, sa.ForeignKey("crm_email_sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("template_id", UUID, sa.ForeignKey("crm_email_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delay_hours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wait_for_open", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("stop_on_reply", sa.Boolean(), server_default="true", nullable=False),
        *_ts(),
    )
    op.create_index("ix_crm_email_sequence_steps_sequence_id", "crm_email_sequence_steps", ["sequence_id"])

    op.create_table(
        "crm_email_enrollments",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("sequence_id", UUID, sa.ForeignKey("crm_email_sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(12), server_default="active", nullable=False),
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", UUID, sa.ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enrolled_by_user_id", sa.String(255), nullable=True),
        *_ts(),
    )
    for col in ("brand_id", "sequence_id", "status", "next_run_at", "contact_id"):
        op.create_index(f"ix_crm_email_enrollments_{col}", "crm_email_enrollments", [col])

    op.create_table(
        "crm_emails",
        sa.Column("id", UUID, primary_key=True), *_tenant(),
        sa.Column("template_id", UUID, sa.ForeignKey("crm_email_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence_id", UUID, sa.ForeignKey("crm_email_sequences.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("crm_email_enrollments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), server_default="draft", nullable=False),
        sa.Column("track_token", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("click_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", UUID, sa.ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_id", UUID, sa.ForeignKey("crm_activities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_by_user_id", sa.String(255), nullable=True),
        *_ts(),
    )
    for col in ("brand_id", "status", "track_token", "provider_message_id", "to_email",
                "contact_id", "company_id", "deal_id", "lead_id"):
        op.create_index(f"ix_crm_emails_{col}", "crm_emails", [col])


def downgrade() -> None:
    op.drop_table("crm_emails")
    op.drop_table("crm_email_enrollments")
    op.drop_table("crm_email_sequence_steps")
    op.drop_table("crm_email_sequences")
    op.drop_table("crm_email_template_versions")
    op.drop_table("crm_email_templates")
    op.drop_table("crm_email_folders")
