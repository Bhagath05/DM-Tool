"""Widen advisor_outcomes.evaluation_status to varchar(32).

Pre-existing bug (surfaced by the Phase 4B/4C Postgres validation): the column
was ``varchar(16)`` but the evaluator writes ``"insufficient_data"`` (17 chars),
which truncation-errors on insert. The only values are ``pending`` (7),
``evaluated`` (9) and ``insufficient_data`` (17); 32 leaves comfortable margin.
Purely a column-width change — no data rewrite, no constraint changes.

Revision ID: 0079_widen_outcome_status
Revises: 0078_agent_action_approvals
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0079_widen_outcome_status"
down_revision: str | None = "0078_agent_action_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "advisor_outcomes",
        "evaluation_status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="pending",
    )


def downgrade() -> None:
    # Narrowing back can fail if a row holds a value longer than 16 chars
    # (e.g. "insufficient_data"); callers that need a clean downgrade must first
    # resolve such rows. Reversible on data that fits.
    op.alter_column(
        "advisor_outcomes",
        "evaluation_status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="pending",
    )
