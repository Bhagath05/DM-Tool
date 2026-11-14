"""Add business_profiles.economics (Phase 7.20 Stage 2b).

A nullable JSONB column holding the brand's structured Business Economics inputs
(provenance-tagged values: price, costs, LTV inputs, budget, targets, with
currency + reporting period + timestamps). Purely ADDITIVE and REVERSIBLE —
existing business_profiles rows keep NULL; no data is migrated, moved, or
destroyed, and the AI-generated ``analysis`` column is untouched.

Revision ID: 0082_business_profiles_economics
Revises: 0081_strategy_evidence_grounding
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0082_business_profiles_economics"
down_revision: str | None = "0081_strategy_evidence_grounding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_profiles",
        sa.Column("economics", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "economics")
