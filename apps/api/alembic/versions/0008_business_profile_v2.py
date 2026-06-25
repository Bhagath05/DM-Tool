"""business profile v2 - conversational onboarding fields

Revision ID: 0008_business_profile_v2
Revises: 0007_lead_capture
Create Date: 2026-05-23

Phase 2.0 — Conversational Onboarding.

Adds four nullable columns to `business_profiles`:
- business_location           (str | None) — city / region / country freeform
- current_monthly_leads_band  (str | None) — UI-chosen band (e.g. "10-50")
- monthly_budget_band         (str | None) — UI-chosen band (e.g. "100-500")
- primary_goal_text           (str | None) — one-line top growth objective

Why nullable, why additive: every existing row predates this phase and must
keep working. The new onboarding stepper writes these; the legacy wizard
ignores them and continues writing the original columns. Downstream modules
(content/ads/trends/campaigns) read only the original columns, so no other
service is affected.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_business_profile_v2"
down_revision: Union[str, None] = "0007_lead_capture"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "business_profiles",
        sa.Column("business_location", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "business_profiles",
        sa.Column(
            "current_monthly_leads_band", sa.String(length=32), nullable=True
        ),
    )
    op.add_column(
        "business_profiles",
        sa.Column("monthly_budget_band", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "business_profiles",
        sa.Column("primary_goal_text", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "primary_goal_text")
    op.drop_column("business_profiles", "monthly_budget_band")
    op.drop_column("business_profiles", "current_monthly_leads_band")
    op.drop_column("business_profiles", "business_location")
