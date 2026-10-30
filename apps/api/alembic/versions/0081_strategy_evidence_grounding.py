"""Add marketing_strategies.evidence_grounding (Phase 7.15).

A nullable JSONB column holding the server-populated, explainable provenance of
which evidence-graded beliefs informed a strategy (or an INSUFFICIENT_EVIDENCE
marker when the brand holds none). Purely additive and reversible — existing
rows keep NULL; no data is migrated or destroyed.

Revision ID: 0081_strategy_evidence_grounding
Revises: 0080_content_read_permission
Create Date: 2026-10-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0081_strategy_evidence_grounding"
down_revision: str | None = "0080_content_read_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketing_strategies",
        sa.Column("evidence_grounding", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marketing_strategies", "evidence_grounding")
