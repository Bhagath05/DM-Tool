"""billing backend — phase 10.2e

Revision ID: 0027_billing
Revises: 0026_org_invites
Create Date: 2026-06-05

Phase 10.2e — Billing architecture WITHOUT Stripe integration.

Four tables. Each has a single responsibility:

  subscription
    One active row per org. Phase 10.2e provisions Early Access lazily
    on first read (no migration backfill). External Stripe ids are
    nullable — they fill in when real billing ships.

  invoice
    Historical billing periods. Empty for Early Access. The table
    exists so the Settings → Billing UI can render an honest "No
    invoices yet — you're on Early Access" empty state instead of
    a phantom Stripe call.

  usage_event
    Append-only event log. Five `kind` values cover the Phase 10.2e
    scope. New `kind`s require a follow-up migration to extend the
    CHECK — we don't auto-evolve enums.

  billing_upgrade_request
    Honest-placeholder receiver. POST /billing/upgrade-request records
    one of these and the founder sees "We've recorded your interest."
    When real Stripe lands, this becomes the inbox for sales-assisted
    upgrades; until then, it's the only source of "Growth/Scale wanted"
    signal we have.

Hot indexes chosen for the Settings → Billing page:
  - ix_subscription_org           : one-shot lookup of the active sub
  - ix_invoice_org_status         : "show me my open invoices"
  - ix_usage_event_org_kind_time  : "this period's recommendations" stat
  - ix_upgrade_request_org_status : admin inbox view
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0027_billing"
down_revision: Union[str, None] = "0026_org_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Lock-step with aicmo/modules/billing/schemas.py and plan_catalog.py.
_PLAN_SLUGS = ("early_access", "growth", "scale")

_SUBSCRIPTION_STATUSES = (
    "active",      # Phase 10.2e: every Early Access sub is here
    "trialing",    # future
    "past_due",    # future
    "canceled",    # future
)

_INVOICE_STATUSES = (
    "draft",
    "open",
    "paid",
    "void",
    "uncollectible",  # Stripe parlance — reserved for future use
)

# Usage event kinds — pinned by the user's Phase 10.2e spec:
#   csv uploads / leads processed / ai recommendations generated /
#   creative analyses performed / campaigns analyzed
_USAGE_KINDS = (
    "csv_upload",
    "lead_processed",
    "ai_recommendation",
    "creative_analysis",
    "campaign_analysis",
)

_UPGRADE_REQUEST_STATUSES = (
    "pending",     # default — founder clicked, we haven't acted yet
    "contacted",   # sales reached out
    "converted",   # closed → real subscription created
    "declined",    # founder changed their mind / didn't pursue
)


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. subscription — one active row per org
    # -----------------------------------------------------------------
    op.create_table(
        "subscription",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # one active sub per org
        ),
        sa.Column(
            "plan_slug",
            sa.String(32),
            nullable=False,
            server_default="early_access",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        # Period boundaries are NULLABLE — Early Access has no period
        # (unlimited, no renewal). When a paid plan kicks in, Stripe's
        # webhook fills these with the current invoice period.
        sa.Column(
            "period_start", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "period_end", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "trial_ends_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "canceled_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Stripe references — nullable; populated when real billing lands.
        sa.Column(
            "external_subscription_id",
            sa.String(128),
            nullable=True,
            comment="Stripe subscription id; null while on Early Access.",
        ),
        sa.Column(
            "external_customer_id",
            sa.String(128),
            nullable=True,
            comment="Stripe customer id; null while on Early Access.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    quoted_plans = ", ".join(f"'{p}'" for p in _PLAN_SLUGS)
    op.execute(
        "ALTER TABLE subscription "
        "ADD CONSTRAINT ck_subscription_plan_slug "
        f"CHECK (plan_slug IN ({quoted_plans}))"
    )
    quoted_statuses = ", ".join(f"'{s}'" for s in _SUBSCRIPTION_STATUSES)
    op.execute(
        "ALTER TABLE subscription "
        "ADD CONSTRAINT ck_subscription_status "
        f"CHECK (status IN ({quoted_statuses}))"
    )

    # -----------------------------------------------------------------
    # 2. invoice — historical billing periods
    # -----------------------------------------------------------------
    op.create_table(
        "invoice",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription.id", ondelete="SET NULL"),
            nullable=True,
            comment="SET NULL — keep invoices visible if a sub is rebuilt.",
        ),
        sa.Column(
            "number",
            sa.String(64),
            nullable=False,
            comment="Human-readable id rendered on the page (e.g. 'INV-2026-0042').",
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "amount_total_cents",
            sa.BigInteger(),
            nullable=False,
            comment="Always stored in minor units (cents). Display layer formats.",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="USD",
        ),
        sa.Column(
            "period_start", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "period_end", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "external_invoice_id",
            sa.String(128),
            nullable=True,
            unique=True,
            comment="Stripe invoice id. UNIQUE so a webhook replay can't double-insert.",
        ),
        sa.Column(
            "hosted_invoice_url",
            sa.Text(),
            nullable=True,
            comment="Stripe-hosted invoice URL. Never null in production; null in dev.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    quoted_inv_statuses = ", ".join(f"'{s}'" for s in _INVOICE_STATUSES)
    op.execute(
        "ALTER TABLE invoice "
        "ADD CONSTRAINT ck_invoice_status "
        f"CHECK (status IN ({quoted_inv_statuses}))"
    )
    op.execute(
        "ALTER TABLE invoice "
        "ADD CONSTRAINT ck_invoice_amount_nonnegative "
        "CHECK (amount_total_cents >= 0)"
    )
    op.execute(
        "ALTER TABLE invoice "
        "ADD CONSTRAINT ck_invoice_currency_iso "
        "CHECK (currency ~ '^[A-Z]{3}$')"
    )
    # Paid-status invariant: paid_at must be set IFF status=paid.
    op.execute(
        "ALTER TABLE invoice "
        "ADD CONSTRAINT ck_invoice_paid_pair "
        "CHECK ((status = 'paid') = (paid_at IS NOT NULL))"
    )

    op.create_index(
        "ix_invoice_org_status",
        "invoice",
        ["organization_id", "status", sa.text("period_end DESC")],
    )

    # -----------------------------------------------------------------
    # 3. usage_event — append-only event log
    # -----------------------------------------------------------------
    op.create_table(
        "usage_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # user_id NULLABLE — background jobs (CSV ingest worker, daily
        # rollups) don't have a user context. We still want to count
        # the event against the org.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # brand_id NULLABLE — org-level events (e.g. AI recommendations
        # at the workspace dashboard) don't belong to a single brand.
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Most events are 1; batch processors may emit >1 in a single row.",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Event-specific extras (e.g. csv_row_count, "
                "recommendation_confidence_band). MUST NOT contain PII "
                "or anything billing should NOT see."
            ),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    quoted_kinds = ", ".join(f"'{k}'" for k in _USAGE_KINDS)
    op.execute(
        "ALTER TABLE usage_event "
        "ADD CONSTRAINT ck_usage_event_kind "
        f"CHECK (kind IN ({quoted_kinds}))"
    )
    op.execute(
        "ALTER TABLE usage_event "
        "ADD CONSTRAINT ck_usage_event_quantity_positive "
        "CHECK (quantity > 0)"
    )

    # Hot path: "summarize usage for this org, this period, by kind."
    op.create_index(
        "ix_usage_event_org_kind_time",
        "usage_event",
        ["organization_id", "kind", sa.text("occurred_at DESC")],
    )

    # -----------------------------------------------------------------
    # 4. billing_upgrade_request — honest placeholder receiver
    # -----------------------------------------------------------------
    op.create_table(
        "billing_upgrade_request",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_plan_slug",
            sa.String(32),
            nullable=False,
            comment="Which plan the founder asked for. CHECK enforced.",
        ),
        sa.Column(
            "current_plan_slug",
            sa.String(32),
            nullable=False,
            comment="What they're on now — for sales context.",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "note",
            sa.Text(),
            nullable=True,
            comment="Optional founder-provided note (e.g. 'need this by Q3').",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "ALTER TABLE billing_upgrade_request "
        "ADD CONSTRAINT ck_upgrade_request_plan_slug "
        f"CHECK (requested_plan_slug IN ({quoted_plans}) "
        f"  AND current_plan_slug IN ({quoted_plans}))"
    )
    quoted_req_statuses = ", ".join(
        f"'{s}'" for s in _UPGRADE_REQUEST_STATUSES
    )
    op.execute(
        "ALTER TABLE billing_upgrade_request "
        "ADD CONSTRAINT ck_upgrade_request_status "
        f"CHECK (status IN ({quoted_req_statuses}))"
    )

    op.create_index(
        "ix_upgrade_request_org_status",
        "billing_upgrade_request",
        ["organization_id", "status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_upgrade_request_org_status",
        table_name="billing_upgrade_request",
    )
    op.execute(
        "ALTER TABLE billing_upgrade_request "
        "DROP CONSTRAINT IF EXISTS ck_upgrade_request_status"
    )
    op.execute(
        "ALTER TABLE billing_upgrade_request "
        "DROP CONSTRAINT IF EXISTS ck_upgrade_request_plan_slug"
    )
    op.drop_table("billing_upgrade_request")

    op.drop_index("ix_usage_event_org_kind_time", table_name="usage_event")
    op.execute(
        "ALTER TABLE usage_event "
        "DROP CONSTRAINT IF EXISTS ck_usage_event_quantity_positive"
    )
    op.execute(
        "ALTER TABLE usage_event "
        "DROP CONSTRAINT IF EXISTS ck_usage_event_kind"
    )
    op.drop_table("usage_event")

    op.drop_index("ix_invoice_org_status", table_name="invoice")
    for c in (
        "ck_invoice_paid_pair",
        "ck_invoice_currency_iso",
        "ck_invoice_amount_nonnegative",
        "ck_invoice_status",
    ):
        op.execute(f"ALTER TABLE invoice DROP CONSTRAINT IF EXISTS {c}")
    op.drop_table("invoice")

    for c in ("ck_subscription_status", "ck_subscription_plan_slug"):
        op.execute(f"ALTER TABLE subscription DROP CONSTRAINT IF EXISTS {c}")
    op.drop_table("subscription")
