"""Tenant-scoped performance indexes — Phase DB-PERF

Revision ID: 0031_tenant_perf_idx
Revises: 0030_ai_audit_events
Create Date: 2026-06-11

Adds composite indexes aligned with the ACTUAL post-tenancy query shapes.

Why this migration exists:
- Pre-tenancy (Phase pre-W1), list queries filtered by `user_id`, so the
  composite indexes were `(user_id, created_at)` / `(user_id, status)`.
- Post-tenancy (W1-11), every service module filters by `brand_id` (and
  org-level reporting by `organization_id`), ORDER BY created_at DESC.
  The legacy user_id indexes no longer match the WHERE clause, so those
  lists fall back to the single-column `brand_id` index + a sort.
- Foreign keys are NOT auto-indexed by Postgres. `audit_events.organization_id`,
  `organizations.owner_user_id`, and the org-member resolution columns had
  no covering index, so the tenant-resolution hot path (run on EVERY
  authenticated request) and the org activity report did sequential-ish work.

All indexes are ADDITIVE and created `IF NOT EXISTS`. No column changes,
no data migration, fully reversible. Tenant isolation is unaffected — these
only make the existing brand_id/organization_id filters faster.

NOTE for production roll-out on large tables:
  These run as plain `CREATE INDEX` inside Alembic's transaction, which
  takes a brief ACCESS EXCLUSIVE-style share lock. Current tables are
  small so this is instant. When any table exceeds ~1M rows, switch the
  relevant statements to `CREATE INDEX CONCURRENTLY` (outside a txn —
  see docs/database/POSTGRES_ARCHITECTURE.md §"Index rollout on large tables").
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0031_tenant_perf_idx"
down_revision: Union[str, None] = "0030_ai_audit_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, raw CREATE INDEX body). Kept as raw SQL so we can express
# DESC ordering and partial predicates the ORM index helper can't.
_INDEXES: tuple[tuple[str, str], ...] = (
    # ---- leads: list by brand, filter by status, order by recency ----
    (
        "ix_leads_brand_created",
        "CREATE INDEX IF NOT EXISTS ix_leads_brand_created "
        "ON leads (brand_id, created_at DESC)",
    ),
    (
        "ix_leads_brand_status",
        "CREATE INDEX IF NOT EXISTS ix_leads_brand_status "
        "ON leads (brand_id, status)",
    ),
    (
        "ix_leads_org_created",
        "CREATE INDEX IF NOT EXISTS ix_leads_org_created "
        "ON leads (organization_id, created_at DESC)",
    ),
    # ---- campaign_plans ----
    (
        "ix_campaign_plans_brand_created",
        "CREATE INDEX IF NOT EXISTS ix_campaign_plans_brand_created "
        "ON campaign_plans (brand_id, created_at DESC)",
    ),
    (
        "ix_campaign_plans_brand_type",
        "CREATE INDEX IF NOT EXISTS ix_campaign_plans_brand_type "
        "ON campaign_plans (brand_id, campaign_type)",
    ),
    (
        "ix_campaign_plans_brand_saved",
        "CREATE INDEX IF NOT EXISTS ix_campaign_plans_brand_saved "
        "ON campaign_plans (brand_id, created_at DESC) WHERE is_saved",
    ),
    # ---- generated_content ----
    (
        "ix_generated_content_brand_created",
        "CREATE INDEX IF NOT EXISTS ix_generated_content_brand_created "
        "ON generated_content (brand_id, created_at DESC)",
    ),
    (
        "ix_generated_content_brand_type",
        "CREATE INDEX IF NOT EXISTS ix_generated_content_brand_type "
        "ON generated_content (brand_id, content_type)",
    ),
    (
        "ix_generated_content_brand_saved",
        "CREATE INDEX IF NOT EXISTS ix_generated_content_brand_saved "
        "ON generated_content (brand_id, created_at DESC) WHERE is_saved",
    ),
    # ---- generated_ads ----
    (
        "ix_generated_ads_brand_created",
        "CREATE INDEX IF NOT EXISTS ix_generated_ads_brand_created "
        "ON generated_ads (brand_id, created_at DESC)",
    ),
    (
        "ix_generated_ads_brand_type",
        "CREATE INDEX IF NOT EXISTS ix_generated_ads_brand_type "
        "ON generated_ads (brand_id, ad_type)",
    ),
    (
        "ix_generated_ads_brand_saved",
        "CREATE INDEX IF NOT EXISTS ix_generated_ads_brand_saved "
        "ON generated_ads (brand_id, created_at DESC) WHERE is_saved",
    ),
    # ---- audit_events: org activity report + actor lookups ----
    (
        "ix_audit_events_org_occurred",
        "CREATE INDEX IF NOT EXISTS ix_audit_events_org_occurred "
        "ON audit_events (organization_id, occurred_at DESC)",
    ),
    (
        "ix_audit_events_actor",
        "CREATE INDEX IF NOT EXISTS ix_audit_events_actor "
        "ON audit_events (actor_user_id)",
    ),
    (
        "ix_audit_events_brand",
        "CREATE INDEX IF NOT EXISTS ix_audit_events_brand "
        "ON audit_events (brand_id) WHERE brand_id IS NOT NULL",
    ),
    # ---- organizations: ownership + status filtering ----
    (
        "ix_organizations_owner",
        "CREATE INDEX IF NOT EXISTS ix_organizations_owner "
        "ON organizations (owner_user_id)",
    ),
    (
        "ix_organizations_active",
        "CREATE INDEX IF NOT EXISTS ix_organizations_active "
        "ON organizations (status) WHERE status = 'active'",
    ),
    # ---- organization_members: tenant-resolution hot path (every request) ----
    (
        "ix_org_members_user_status",
        "CREATE INDEX IF NOT EXISTS ix_org_members_user_status "
        "ON organization_members (user_id, status)",
    ),
    (
        "ix_org_members_org_user",
        "CREATE INDEX IF NOT EXISTS ix_org_members_org_user "
        "ON organization_members (organization_id, user_id)",
    ),
)


def upgrade() -> None:
    for _name, ddl in _INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for name, _ddl in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
