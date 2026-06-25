"""Billing live — DB-configurable plans/quotas + Stripe idempotency — Phase 1

Revision ID: 0033_billing_live
Revises: 0032_rls_policies
Create Date: 2026-06-11

Makes plans + usage limits the system of record in PostgreSQL, so
pricing/quotas are tunable WITHOUT a code change or migration:

  - `plan`        — one row per plan (slug, display copy, price, Stripe
                    price id, availability, default flag). Adding a plan
                    is an INSERT, not a migration.
  - `plan_quota`  — per-(plan, usage_kind) monthly limit. NULL = unlimited.
                    Tuning a limit is an UPDATE.

Plus Stripe plumbing:
  - `stripe_event` — webhook idempotency log (event id unique).
  - extend `usage_event.kind` CHECK with the 3 product-metered kinds
    (`generation`, `campaign`, `lead`) used by the new quota model.
  - swap `subscription.plan_slug` / `billing_upgrade_request` plan CHECKs
    for FOREIGN KEYs to `plan.slug` — so new plans need no migration.

Seeded plans (placeholder, all tunable later):
  early_access — unlimited, default, current users (BACKWARD COMPAT)
  free         — 100 generations / 10 campaigns / 25 leads
  starter      — 2,000 / 100 / 500
  growth       — 15,000 / 500 / 5,000
  scale        — unlimited (custom)

Reversible: downgrade restores the original CHECKs and drops the new
tables/columns. subscription/invoice DATA is never touched.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0033_billing_live"
down_revision: Union[str, None] = "0032_rls_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Product-metered kinds added to the usage_event CHECK (existing 5 kept).
_NEW_USAGE_KINDS = ("generation", "campaign", "lead")
_EXISTING_USAGE_KINDS = (
    "csv_upload",
    "lead_processed",
    "ai_recommendation",
    "creative_analysis",
    "campaign_analysis",
)
_ALL_USAGE_KINDS = _EXISTING_USAGE_KINDS + _NEW_USAGE_KINDS

# Seed data. (slug, name, tagline, price_cents, availability, is_default, sort)
_PLANS = (
    ("early_access", "Early Access", "Everything unlocked while you shape the product.", None, "current", True, 0),
    ("free", "Free", "Get started — no card required.", 0, "upcoming", False, 1),
    ("starter", "Starter", "For founders getting consistent.", 2900, "upcoming", False, 2),
    ("growth", "Growth", "For businesses scaling output.", 9900, "upcoming", False, 3),
    ("scale", "Scale", "Custom volume for teams + agencies.", None, "upcoming", False, 4),
)

# (plan_slug, usage_kind, monthly_limit). NULL/absent = unlimited.
_QUOTAS = (
    ("free", "generation", 100),
    ("free", "campaign", 10),
    ("free", "lead", 25),
    ("starter", "generation", 2000),
    ("starter", "campaign", 100),
    ("starter", "lead", 500),
    ("growth", "generation", 15000),
    ("growth", "campaign", 500),
    ("growth", "lead", 5000),
    # early_access + scale: no rows => unlimited.
)


def upgrade() -> None:
    # 1. plan table -----------------------------------------------------
    op.create_table(
        "plan",
        sa.Column("slug", sa.String(32), primary_key=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("monthly_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("stripe_price_id", sa.String(128), nullable=True),
        sa.Column("availability", sa.String(16), nullable=False, server_default="upcoming"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # At most one default plan.
    op.execute(
        "CREATE UNIQUE INDEX uq_plan_one_default ON plan (is_default) WHERE is_default = true"
    )

    plan_tbl = sa.table(
        "plan",
        sa.column("slug"), sa.column("display_name"), sa.column("tagline"),
        sa.column("monthly_price_cents"), sa.column("availability"),
        sa.column("is_default"), sa.column("sort_order"),
    )
    op.bulk_insert(
        plan_tbl,
        [
            {
                "slug": s, "display_name": n, "tagline": t,
                "monthly_price_cents": p, "availability": a,
                "is_default": d, "sort_order": o,
            }
            for (s, n, t, p, a, d, o) in _PLANS
        ],
    )

    # 2. plan_quota table ----------------------------------------------
    op.create_table(
        "plan_quota",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_slug", sa.String(32), sa.ForeignKey("plan.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_kind", sa.String(32), nullable=False),
        sa.Column("monthly_limit", sa.Integer(), nullable=True),  # NULL = unlimited
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("plan_slug", "usage_kind", name="uq_plan_quota_plan_kind"),
    )
    quota_tbl = sa.table(
        "plan_quota",
        sa.column("plan_slug"), sa.column("usage_kind"), sa.column("monthly_limit"),
    )
    op.bulk_insert(
        quota_tbl,
        [
            {"plan_slug": ps, "usage_kind": k, "monthly_limit": lim}
            for (ps, k, lim) in _QUOTAS
        ],
    )

    # 3. stripe_event idempotency log ----------------------------------
    op.create_table(
        "stripe_event",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 4. extend usage_event.kind CHECK ---------------------------------
    quoted = ", ".join(f"'{k}'" for k in _ALL_USAGE_KINDS)
    op.execute("ALTER TABLE usage_event DROP CONSTRAINT IF EXISTS ck_usage_event_kind")
    op.execute(
        f"ALTER TABLE usage_event ADD CONSTRAINT ck_usage_event_kind CHECK (kind IN ({quoted}))"
    )

    # 5. plan_slug CHECKs -> FKs to plan.slug --------------------------
    op.execute("ALTER TABLE subscription DROP CONSTRAINT IF EXISTS ck_subscription_plan_slug")
    op.create_foreign_key(
        "fk_subscription_plan", "subscription", "plan",
        ["plan_slug"], ["slug"], ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE billing_upgrade_request DROP CONSTRAINT IF EXISTS ck_upgrade_request_plan_slug"
    )
    op.create_foreign_key(
        "fk_upgrade_request_requested_plan", "billing_upgrade_request", "plan",
        ["requested_plan_slug"], ["slug"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_upgrade_request_current_plan", "billing_upgrade_request", "plan",
        ["current_plan_slug"], ["slug"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Restore the original plan-slug CHECKs (3 plans) and drop FKs.
    orig_plans = ("early_access", "growth", "scale")
    quoted_plans = ", ".join(f"'{p}'" for p in orig_plans)

    op.drop_constraint("fk_upgrade_request_current_plan", "billing_upgrade_request", type_="foreignkey")
    op.drop_constraint("fk_upgrade_request_requested_plan", "billing_upgrade_request", type_="foreignkey")
    op.drop_constraint("fk_subscription_plan", "subscription", type_="foreignkey")
    op.execute(
        "ALTER TABLE billing_upgrade_request ADD CONSTRAINT ck_upgrade_request_plan_slug "
        f"CHECK (requested_plan_slug IN ({quoted_plans}) AND current_plan_slug IN ({quoted_plans}))"
    )
    op.execute(
        f"ALTER TABLE subscription ADD CONSTRAINT ck_subscription_plan_slug CHECK (plan_slug IN ({quoted_plans}))"
    )

    # Restore the original usage_event.kind CHECK (5 kinds).
    quoted_kinds = ", ".join(f"'{k}'" for k in _EXISTING_USAGE_KINDS)
    op.execute("ALTER TABLE usage_event DROP CONSTRAINT IF EXISTS ck_usage_event_kind")
    op.execute(
        f"ALTER TABLE usage_event ADD CONSTRAINT ck_usage_event_kind CHECK (kind IN ({quoted_kinds}))"
    )

    op.drop_table("stripe_event")
    op.drop_table("plan_quota")
    op.execute("DROP INDEX IF EXISTS uq_plan_one_default")
    op.drop_table("plan")
