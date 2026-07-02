"""Phase 3.10 — autonomy_level column (Future Autonomy Flags).

Adds the progressive-autonomy LEVEL to autonomy_policies. Additive column with a
constant server_default ("manual") → no table rewrite (Postgres 11+), and the
default keeps every existing/absent policy fully manual.

Revision ID: 0050_autonomy_level
Revises: 0049_autonomy_policies
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050_autonomy_level"
down_revision: Union[str, None] = "0049_autonomy_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autonomy_policies",
        sa.Column(
            "autonomy_level",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("autonomy_policies", "autonomy_level")
