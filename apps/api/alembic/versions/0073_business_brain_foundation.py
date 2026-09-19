"""Business Brain foundation — research jobs, evidence, ICP hypotheses.

Revision ID: 0073_business_brain_foundation
Revises: 0072_first_party_auth
Create Date: 2026-09-15

Additive only. Does not modify auth tables or 0072.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from aicmo.db import rls
from alembic import op

revision: str = "0073_business_brain_foundation"
down_revision: str | None = "0072_first_party_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Dormant org-scoped RLS policies (same pattern as creative migrations).
# ENABLE/FORCE still happens via scripts/rls_activate.py.
_TENANT_TABLES: tuple[str, ...] = (
    "brain_research_jobs",
    "brain_evidence",
    "brain_icps",
    "brain_icp_evidence",
)


def upgrade() -> None:
    op.create_table(
        "brain_research_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="website"),
        sa.Column("input_url", sa.String(500), nullable=False),
        sa.Column("normalized_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "discovery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("website_discoveries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_brain_research_jobs_brand_id", "brain_research_jobs", ["brand_id"]
    )
    op.create_index(
        "ix_brain_research_jobs_organization_id",
        "brain_research_jobs",
        ["organization_id"],
    )
    op.create_index(
        "ix_brain_research_jobs_brand_status",
        "brain_research_jobs",
        ["brand_id", "status"],
    )
    op.create_index(
        "uq_brain_research_jobs_active",
        "brain_research_jobs",
        ["brand_id", "kind", "normalized_url"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "brain_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_research_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("claim", sa.String(1000), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="website"),
        sa.Column("snippet", sa.String(800), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_brain_evidence_brand_id", "brain_evidence", ["brand_id"])
    op.create_index(
        "ix_brain_evidence_organization_id", "brain_evidence", ["organization_id"]
    )
    op.create_index(
        "ix_brain_evidence_brand_kind", "brain_evidence", ["brand_id", "kind"]
    )
    op.create_index(
        "ix_brain_evidence_brand_category", "brain_evidence", ["brand_id", "category"]
    )
    op.create_index(
        "ix_brain_evidence_research_job", "brain_evidence", ["research_job_id"]
    )

    op.create_table(
        "brain_icps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "industries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("company_size", sa.String(120), nullable=True),
        sa.Column(
            "geography",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "buyer_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "pain_points",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "buying_signals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "exclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("status", sa.String(16), nullable=False, server_default="hypothesis"),
        sa.Column(
            "research_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_research_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_brain_icps_brand_id", "brain_icps", ["brand_id"])
    op.create_index("ix_brain_icps_organization_id", "brain_icps", ["organization_id"])
    op.create_index(
        "ix_brain_icps_brand_status", "brain_icps", ["brand_id", "status"]
    )

    op.create_table(
        "brain_icp_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "icp_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_icps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_evidence.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("icp_id", "evidence_id", name="uq_brain_icp_evidence"),
    )
    op.create_index("ix_brain_icp_evidence_brand_id", "brain_icp_evidence", ["brand_id"])
    op.create_index("ix_brain_icp_evidence_icp", "brain_icp_evidence", ["icp_id"])

    for table in _TENANT_TABLES:
        op.execute(rls.create_policy_sql(table))


def downgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(rls.drop_policy_sql(table))

    op.drop_index("ix_brain_icp_evidence_icp", table_name="brain_icp_evidence")
    op.drop_index("ix_brain_icp_evidence_brand_id", table_name="brain_icp_evidence")
    op.drop_table("brain_icp_evidence")

    op.drop_index("ix_brain_icps_brand_status", table_name="brain_icps")
    op.drop_index("ix_brain_icps_organization_id", table_name="brain_icps")
    op.drop_index("ix_brain_icps_brand_id", table_name="brain_icps")
    op.drop_table("brain_icps")

    op.drop_index("ix_brain_evidence_research_job", table_name="brain_evidence")
    op.drop_index("ix_brain_evidence_brand_category", table_name="brain_evidence")
    op.drop_index("ix_brain_evidence_brand_kind", table_name="brain_evidence")
    op.drop_index("ix_brain_evidence_organization_id", table_name="brain_evidence")
    op.drop_index("ix_brain_evidence_brand_id", table_name="brain_evidence")
    op.drop_table("brain_evidence")

    op.drop_index("uq_brain_research_jobs_active", table_name="brain_research_jobs")
    op.drop_index("ix_brain_research_jobs_brand_status", table_name="brain_research_jobs")
    op.drop_index(
        "ix_brain_research_jobs_organization_id", table_name="brain_research_jobs"
    )
    op.drop_index("ix_brain_research_jobs_brand_id", table_name="brain_research_jobs")
    op.drop_table("brain_research_jobs")
