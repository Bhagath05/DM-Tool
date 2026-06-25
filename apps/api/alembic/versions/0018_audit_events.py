"""audit events

Revision ID: 0018_audit_events
Revises: 0017_tenant_not_null
Create Date: 2026-05-30

Single table for the audit log. Writers wired into every mutation in
orgs/brands/rbac services. Reader UI is a later slice; the writes need
to start now because audit logs missed at the start cannot be
backfilled.

Indices favour:
  - by-org timeline   (org dashboard / compliance)
  - by-actor timeline (user activity inspection)
  - by-action timeline (security forensics)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_audit_events"
down_revision: Union[str, None] = "0017_tenant_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_org_occurred",
        "audit_events",
        ["organization_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_actor_occurred",
        "audit_events",
        ["actor_user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_action_occurred",
        "audit_events",
        ["action", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_events_action_occurred", table_name="audit_events"
    )
    op.drop_index(
        "ix_audit_events_actor_occurred", table_name="audit_events"
    )
    op.drop_index(
        "ix_audit_events_org_occurred", table_name="audit_events"
    )
    op.drop_table("audit_events")
