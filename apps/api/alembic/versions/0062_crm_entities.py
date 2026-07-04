"""Phase 6.5 Slice 2 — CRM entities: companies, contacts, activities.

3 new tenant-scoped tables (crm_companies / crm_contacts / crm_activities) + a
deal↔contacts join (crm_deal_contacts) + 2 additive nullable FKs on crm_deals
(company_id, primary_contact_id). Backward compatible — Slice-1 deals keep their
embedded company/contact strings; the new links default NULL.

Revision ID: 0062_crm_entities
Revises: 0061_crm_core
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0062_crm_entities"
down_revision: str | None = "0061_crm_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _tenant_cols() -> list[sa.Column]:
    return [
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
    ]


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "crm_companies",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("industry", sa.String(120), nullable=True),
        sa.Column("annual_revenue", sa.Numeric(16, 2), nullable=True),
        sa.Column("employees", sa.Integer(), nullable=True),
        sa.Column("tech_stack", JSONB, server_default="[]", nullable=False),
        sa.Column("social_links", JSONB, server_default="{}", nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(48), nullable=True),
        sa.Column("owner_user_id", sa.String(255), nullable=True),
        sa.Column("tags", JSONB, server_default="[]", nullable=False),
        sa.Column("custom_fields", JSONB, server_default="{}", nullable=False),
        sa.Column("ai_summary", JSONB, nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("health_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
        *_ts_cols(),
    )
    for col in ("brand_id", "name", "domain", "owner_user_id", "archived"):
        op.create_index(f"ix_crm_companies_{col}", "crm_companies", [col])

    op.create_table(
        "crm_contacts",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(160), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("linkedin", sa.String(512), nullable=True),
        sa.Column("owner_user_id", sa.String(255), nullable=True),
        sa.Column("tags", JSONB, server_default="[]", nullable=False),
        sa.Column("custom_fields", JSONB, server_default="{}", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ai_summary", JSONB, nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
        *_ts_cols(),
    )
    for col in ("brand_id", "company_id", "lead_id", "name", "email", "owner_user_id", "archived"):
        op.create_index(f"ix_crm_contacts_{col}", "crm_contacts", [col])

    op.create_table(
        "crm_activities",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(240), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", sa.String(255), nullable=True),
        sa.Column("meta", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for col in ("brand_id", "kind", "contact_id", "company_id", "deal_id", "occurred_at"):
        op.create_index(f"ix_crm_activities_{col}", "crm_activities", [col])

    op.create_table(
        "crm_deal_contacts",
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="CASCADE"), primary_key=True),
        *_tenant_cols(),
        sa.Column("role", sa.String(48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_deal_contacts_contact_id", "crm_deal_contacts", ["contact_id"])

    # Additive deal associations (backward compatible — nullable).
    op.add_column("crm_deals", sa.Column("company_id", UUID, sa.ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True))
    op.add_column("crm_deals", sa.Column("primary_contact_id", UUID, sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_crm_deals_company_id", "crm_deals", ["company_id"])
    op.create_index("ix_crm_deals_primary_contact_id", "crm_deals", ["primary_contact_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_deals_primary_contact_id", table_name="crm_deals")
    op.drop_index("ix_crm_deals_company_id", table_name="crm_deals")
    op.drop_column("crm_deals", "primary_contact_id")
    op.drop_column("crm_deals", "company_id")
    op.drop_table("crm_deal_contacts")
    op.drop_table("crm_activities")
    op.drop_table("crm_contacts")
    op.drop_table("crm_companies")
