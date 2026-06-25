"""organization profile fields — phase 10.2f

Revision ID: 0028_org_profile
Revises: 0027_billing
Create Date: 2026-06-05

Phase 10.2f — Extends the `organizations` table with profile metadata.

Five new nullable columns. All optional in the DB so a freshly-created
org (from the existing onboarding wizard) doesn't need to know them at
creation time — they fill in via Settings → Organization later.

  logo_url    TEXT      — Public URL to the org logo. Pydantic HttpUrl
                          validates format at the API boundary.
  website     TEXT      — Public URL to the org website.
  industry    VARCHAR   — Free-form (e.g. 'D2C apparel', 'SaaS').
                          Free-form rather than enum because:
                            1. The AI Coach reasons over this string as
                               natural language — an enum would bottleneck.
                            2. We don't want the founder hitting "Other"
                               and stalling.
  timezone    VARCHAR   — IANA timezone (e.g. 'America/New_York'). Full
                          IANA validation lives in Pydantic — a CHECK
                          constraint can't enumerate every valid zone.
  country     VARCHAR(2)— ISO-3166 alpha-2. CHECK enforces format.
                          Enables future currency resolution (per the
                          Constitution: "Never hardcode INR — use account
                          currency"). Wiring lands in a later phase.

No backfill. Existing orgs keep NULL across these fields until their
owner fills them in.

Rollback drops the columns. No data loss beyond the profile values
themselves — every other org concern (members, brands, billing) is
untouched.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028_org_profile"
down_revision: Union[str, None] = "0027_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("logo_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("website", sa.Text(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("industry", sa.String(64), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("timezone", sa.String(64), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("country", sa.String(2), nullable=True),
    )

    # ISO-3166 alpha-2 — exactly 2 uppercase letters. Null-tolerant.
    # Strict format check at the DB layer means a buggy service can't
    # store 'india' or 'IN-IN' by accident.
    op.execute(
        "ALTER TABLE organizations "
        "ADD CONSTRAINT ck_organizations_country_iso2 "
        "CHECK (country IS NULL OR country ~ '^[A-Z]{2}$')"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE organizations "
        "DROP CONSTRAINT IF EXISTS ck_organizations_country_iso2"
    )
    op.drop_column("organizations", "country")
    op.drop_column("organizations", "timezone")
    op.drop_column("organizations", "industry")
    op.drop_column("organizations", "website")
    op.drop_column("organizations", "logo_url")
