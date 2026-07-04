"""Phase 6.5 — CRM core: pipelines, stages, deals + crm permissions.

4 new tenant-scoped tables (crm_pipelines / crm_pipeline_stages / crm_deals /
crm_deal_stage_events) + 2 new RBAC permissions (crm.view / crm.manage) seeded
into the system roles. Deals link (nullable, SET NULL) to the EXISTING leads
row — reuse, no duplicate person record. Additive throughout.

Revision ID: 0061_crm_core
Revises: 0060_publishing_ops
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0061_crm_core"
down_revision: str | None = "0060_publishing_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

_NEW_PERMISSIONS = [
    ("crm.view", "View CRM", "See pipelines, deals, and CRM analytics.", "crm"),
    ("crm.manage", "Manage CRM", "Create and edit pipelines, stages, and deals.", "crm"),
]
# owner gets everything anyway (all-perms), but seed explicitly for admin/editor/
# viewer so the CRM is usable by the standard roles out of the box.
_ROLE_GRANTS = {
    "admin": ["crm.view", "crm.manage"],
    "editor": ["crm.view", "crm.manage"],
    "viewer": ["crm.view"],
    "owner": ["crm.view", "crm.manage"],
    "analyst": ["crm.view"],
}


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
        "crm_pipelines",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), server_default="sales", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_crm_pipelines_brand_id", "crm_pipelines", ["brand_id"])
    op.create_index("ix_crm_pipelines_archived", "crm_pipelines", ["archived"])

    op.create_table(
        "crm_pipeline_stages",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("pipeline_id", UUID, sa.ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("probability", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_won", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_lost", sa.Boolean(), server_default="false", nullable=False),
        *_ts_cols(),
    )
    op.create_index("ix_crm_pipeline_stages_pipeline_id", "crm_pipeline_stages", ["pipeline_id"])
    op.create_index("ix_crm_pipeline_stages_brand_id", "crm_pipeline_stages", ["brand_id"])

    op.create_table(
        "crm_deals",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("pipeline_id", UUID, sa.ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", UUID, sa.ForeignKey("crm_pipeline_stages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("company", sa.String(200), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("contact_phone", sa.String(64), nullable=True),
        sa.Column("value", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(12), server_default="open", nullable=False),
        sa.Column("priority", sa.String(8), server_default="medium", nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.String(255), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("tags", JSONB, server_default="[]", nullable=False),
        sa.Column("products", JSONB, server_default="[]", nullable=False),
        sa.Column("competitors", JSONB, server_default="[]", nullable=False),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_next_action", JSONB, nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
    )
    for col in ("brand_id", "pipeline_id", "stage_id", "lead_id", "status", "owner_user_id"):
        op.create_index(f"ix_crm_deals_{col}", "crm_deals", [col])

    op.create_table(
        "crm_deal_stage_events",
        sa.Column("id", UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("deal_id", UUID, sa.ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_stage_id", UUID, nullable=True),
        sa.Column("to_stage_id", UUID, nullable=True),
        sa.Column("from_status", sa.String(12), nullable=True),
        sa.Column("to_status", sa.String(12), nullable=True),
        sa.Column("actor_user_id", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_deal_stage_events_deal_id", "crm_deal_stage_events", ["deal_id"])

    # ----- RBAC: seed crm.view / crm.manage + role grants (idempotent) -----
    bind = op.get_bind()
    for slug, name, description, category in _NEW_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, slug, name, description, category)
                VALUES (gen_random_uuid(), :slug, :name, :description, :category)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"slug": slug, "name": name, "description": description, "category": category},
        )
    for role_slug, perm_slugs in _ROLE_GRANTS.items():
        for perm_slug in perm_slugs:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id FROM roles r, permissions p
                    WHERE r.slug = :role_slug AND r.organization_id IS NULL AND r.is_system = true
                      AND p.slug = :perm_slug
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_slug": role_slug, "perm_slug": perm_slug},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM permissions WHERE slug IN ('crm.view', 'crm.manage')")
    )
    op.drop_table("crm_deal_stage_events")
    op.drop_table("crm_deals")
    op.drop_table("crm_pipeline_stages")
    op.drop_table("crm_pipelines")
