"""Creative Studio (CS1) — editable design model + outcome objective

Revision ID: 0035_creative_studio
Revises: 0034_creative_core
Create Date: 2026-06-15

The Creative Studio spine, dark-launched (studio_enabled=false). Adds the
editable layer-document model + the outcome object that drives it, per
CS1_TECHNICAL_DESIGN.md and the Creative Studio Constitution (CLAUDE.md):

  catalog (non-tenant, RLS-excluded like `creative_format`/`plan`):
      objective_kind        outcome taxonomy — OUTCOME semantics, no industry
      layout_primitive      composition library — generated, never categorized
  tenant (RLS):
      growth_objective              the business outcome (Law 1 primary object)
      creative_design               editable layer doc (head)
      creative_design_revision      immutable, append-only (Law 3 backbone)
      brand_asset                   tenant-owned uploaded assets

Plus: campaign_plans.objective_id FK (nullable, back-compat), dormant RLS
policies on the 4 tenant tables, industry-FREE seeds, and growth.* RBAC
permissions + grants to the global system roles.

Additive + reversible. No existing table data is touched (the one ALTER is
a nullable column). No design mutates in place — every change is a new
creative_design_revision via apply_revision (enforced in app code).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from aicmo.db import rls


revision: str = "0035_creative_studio"
down_revision: Union[str, None] = "0034_creative_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The 4 new tenant tables that get a dormant RLS policy (must be in
# rls.ORG_SCOPED_TABLES so create_policy_sql resolves the org_scoped shape).
_TENANT_TABLES = (
    "growth_objective",
    "creative_design",
    "creative_design_revision",
    "brand_asset",
)

# objective_kind seed — OUTCOME semantics only. No industry, no asset type.
# (slug, display_name, category, kpi_hint, default_channels)
_OBJECTIVE_KINDS = (
    ("get_leads", "Get Leads", "lead", "leads / cost per lead", ["meta", "google", "email"]),
    ("get_bookings", "Get Bookings", "booking", "bookings / cost per booking", ["meta", "google", "whatsapp"]),
    ("drive_sales", "Drive Sales", "sale", "purchases / ROAS", ["meta", "google", "email"]),
    ("grow_awareness", "Grow Awareness", "awareness", "reach / impressions", ["meta", "youtube", "tiktok"]),
    ("drive_installs", "Drive App Installs", "install", "installs / cost per install", ["meta", "google", "tiktok"]),
    ("hire", "Hire / Recruit", "hire", "applications / cost per applicant", ["linkedin", "meta", "email"]),
    ("get_signups", "Get Sign-ups", "signup", "registrations / cost per signup", ["meta", "google", "email"]),
    ("drive_traffic", "Drive Traffic", "traffic", "visits / cost per click", ["google", "meta", "email"]),
    ("retain_customers", "Retain Customers", "retention", "repeat rate / churn", ["email", "whatsapp", "sms"]),
)

# layout_primitive seed — COMPOSITION, parameterized by outcome. No industry.
# objective_affinity keys are objective_kind.category values (outcome semantics).
# (slug, kind, params, objective_affinity)
_LAYOUT_PRIMITIVES = (
    ("single_focal_hero", "focal", {"focal": "center", "depth": "shallow"}, {"sale": 0.9, "install": 0.8, "booking": 0.7}),
    ("strong_offer_hero", "focal", {"focal": "offer", "cta": "dominant"}, {"sale": 1.0, "booking": 0.8}),
    ("credibility_stack", "hierarchy", {"order": ["proof", "value", "cta"]}, {"lead": 0.9, "hire": 0.7}),
    ("social_proof_band", "hierarchy", {"order": ["testimonial", "logo_wall", "cta"]}, {"lead": 0.8, "awareness": 0.6}),
    ("modular_grid", "grid", {"cols": 12, "gutter": 24}, {"awareness": 0.7, "traffic": 0.6}),
    ("type_scale_editorial", "type_scale", {"scale": 1.333, "base": 16}, {"awareness": 0.8, "retention": 0.6}),
    ("color_system_dynamic", "color_system", {"derive_from": "brand_tokens", "mood": "auto"}, {"sale": 0.6, "awareness": 0.6}),
)

_PERMISSIONS = (
    ("growth.create", "Create growth objective", "growth"),
    ("growth.read", "View growth objectives", "growth"),
)
_GRANTS = (
    ("owner", "growth.create"), ("admin", "growth.create"), ("editor", "growth.create"),
    ("owner", "growth.read"), ("admin", "growth.read"), ("editor", "growth.read"),
    ("analyst", "growth.read"), ("viewer", "growth.read"),
)


def _uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _tenant_cols():
    return (
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
    )


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    # ---- objective_kind (catalog, non-tenant) ----
    op.create_table(
        "objective_kind",
        sa.Column("slug", sa.String(48), primary_key=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("kpi_hint", sa.String(128), nullable=True),
        sa.Column("default_channels", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.bulk_insert(
        sa.table(
            "objective_kind",
            sa.column("slug"), sa.column("display_name"), sa.column("category"),
            sa.column("kpi_hint"), sa.column("default_channels", postgresql.JSONB()),
            sa.column("sort_order"),
        ),
        [
            {"slug": s, "display_name": n, "category": c, "kpi_hint": k,
             "default_channels": ch, "sort_order": i}
            for i, (s, n, c, k, ch) in enumerate(_OBJECTIVE_KINDS)
        ],
    )

    # ---- layout_primitive (catalog, non-tenant) ----
    op.create_table(
        "layout_primitive",
        sa.Column("slug", sa.String(48), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("objective_affinity", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.bulk_insert(
        sa.table(
            "layout_primitive",
            sa.column("slug"), sa.column("kind"),
            sa.column("params", postgresql.JSONB()),
            sa.column("objective_affinity", postgresql.JSONB()),
            sa.column("sort_order"),
        ),
        [
            {"slug": s, "kind": k, "params": p, "objective_affinity": aff, "sort_order": i}
            for i, (s, k, p, aff) in enumerate(_LAYOUT_PRIMITIVES)
        ],
    )

    # ---- growth_objective (tenant) — Law 1 primary object ----
    op.create_table(
        "growth_objective",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("business_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("objective_kind", sa.String(48),
                  sa.ForeignKey("objective_kind.slug", ondelete="RESTRICT"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),          # free text (the goal)
        sa.Column("audience_hypothesis", sa.Text(), nullable=True),
        sa.Column("budget_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_growth_objective_brand", "growth_objective", ["brand_id"])
    op.execute(
        "CREATE INDEX ix_growth_objective_active ON growth_objective (brand_id) "
        "WHERE status = 'active'"
    )

    # ---- creative_design (tenant) — the editable head ----
    # head_revision_id is a plain UUID (no DB FK) to avoid a circular FK with
    # creative_design_revision; integrity is maintained by apply_revision.
    op.create_table(
        "creative_design",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("growth_objective_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("growth_objective.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format_slug", sa.String(48),
                  sa.ForeignKey("creative_format.slug", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),     # image|carousel|composite|video
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("head_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_mode", sa.String(8), nullable=False, server_default="ai"),  # ai|guided|pro
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        *_timestamps(),
    )
    op.create_index("ix_creative_design_brand_created", "creative_design",
                    ["brand_id", sa.text("created_at DESC")])
    op.create_index("ix_creative_design_objective", "creative_design", ["growth_objective_id"])

    # ---- creative_design_revision (tenant, append-only) — Law 3 backbone ----
    op.create_table(
        "creative_design_revision",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("design_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_design.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_n", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_design_revision.id", ondelete="SET NULL"), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("ops", postgresql.JSONB(), nullable=True),        # the diff that produced this rev
        sa.Column("source", sa.String(24), nullable=False),         # ai_generate|ai_edit|ai_regenerate|ai_restyle|ai_transform|user_edit|template
        sa.Column("actor_kind", sa.String(8), nullable=False),      # ai|human
        sa.Column("mode", sa.String(8), nullable=False),            # ai|guided|pro
        sa.Column("review_status", sa.String(20), nullable=False, server_default="draft"),  # draft|pending|approved|changes_requested
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(255), nullable=True),
        sa.Column("edit_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("uq_design_revision_n", "creative_design_revision",
                    ["design_id", "revision_n"], unique=True)
    op.create_index("ix_design_revision_parent", "creative_design_revision", ["parent_revision_id"])

    # ---- brand_asset (tenant) — tenant-owned uploads the layer doc references ----
    op.create_table(
        "brand_asset",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),           # logo|font|image|color|icon
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("storage_backend", sa.String(16), nullable=True),  # local|s3
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(48), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("ix_brand_asset_brand_kind", "brand_asset", ["brand_id", "kind"])

    # ---- campaign_plans.objective_id (additive, nullable, back-compat) ----
    op.add_column(
        "campaign_plans",
        sa.Column("objective_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("growth_objective.id", ondelete="SET NULL"), nullable=True),
    )

    # ---- dormant RLS policies on the 4 tenant tables ----
    for table in _TENANT_TABLES:
        op.execute(rls.create_policy_sql(table))

    # ---- RBAC: growth.* permissions + grants to global system roles ----
    for slug, name, cat in _PERMISSIONS:
        op.execute(
            "INSERT INTO permissions (id, slug, name, description, category) "
            f"VALUES (gen_random_uuid(), '{slug}', '{name}', '{name}', '{cat}') "
            "ON CONFLICT (slug) DO NOTHING"
        )
    for role_slug, perm_slug in _GRANTS:
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM roles r, permissions p "
            f"WHERE r.slug = '{role_slug}' AND p.slug = '{perm_slug}' "
            "ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    # RBAC
    perm_slugs = ", ".join(f"'{s}'" for s, _, _ in _PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE slug IN ({perm_slugs}))"
    )
    op.execute(f"DELETE FROM permissions WHERE slug IN ({perm_slugs})")

    # RLS policies
    for table in _TENANT_TABLES:
        op.execute(rls.drop_policy_sql(table))

    # campaign_plans column
    op.drop_column("campaign_plans", "objective_id")

    # tables (children first)
    op.drop_table("brand_asset")
    op.drop_table("creative_design_revision")
    op.drop_table("creative_design")
    op.drop_table("growth_objective")
    op.drop_table("layout_primitive")
    op.drop_table("objective_kind")
