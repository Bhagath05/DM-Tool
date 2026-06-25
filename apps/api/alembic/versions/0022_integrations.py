"""integrations framework — phase 10.2a

Revision ID: 0022_integrations
Revises: 0021_perf_intel_kinds
Create Date: 2026-06-04

Phase 10.2a — Reusable integration framework.

Adds the two-table integration store that every connector (Meta Ads,
Google Ads, LinkedIn, TikTok, HubSpot, Salesforce — and anything we
add later) plugs into. **No Meta-specific schema lives here.**

Two tables on purpose:

  integration_connection   — public metadata: org, brand, provider,
                             state, account name, last sync timestamps.
                             Safe to expose via API.

  integration_credential   — encrypted OAuth tokens, 1:1 with the
                             connection row. Separate table so anyone
                             running `SELECT * FROM integration_connection`
                             in psql can't accidentally see tokens, and
                             so we can grep "credential" to audit
                             every callsite that touches secrets.

State machine values are enforced by a CHECK constraint on the DB
side and a Literal on the Pydantic side. The list is kept in
lock-step with `aicmo/modules/integrations/schemas.py`.

A partial unique index ensures only ONE non-terminal connection per
(organization, brand, provider) tuple — a brand can't accidentally
have two "ACTIVE" Meta connections fighting each other.

Rollback drops both tables. Token data is encrypted at rest, so a
rollback that loses the credential table doesn't expose plaintext
tokens to anyone reading the dump.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0022_integrations"
down_revision: Union[str, None] = "0021_perf_intel_kinds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Connection-state enum — kept in lock-step with:
#   apps/api/aicmo/modules/integrations/schemas.py:ConnectionState
#   apps/web/src/lib/api.ts (Phase 10.2g)
_CONNECTION_STATES = (
    "DISCONNECTED",
    "PENDING_AUTH",
    "ACTIVE",
    "EXPIRED",
    "ERROR",
    "SUSPENDED",
)


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. integration_connection — public, API-safe metadata
    # -----------------------------------------------------------------
    op.create_table(
        "integration_connection",
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
        # brand_id is nullable: some integrations are org-level (HubSpot,
        # Salesforce — one CRM per company) while others are brand-level
        # (each ad account belongs to one brand). The unique index below
        # handles both shapes.
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider_slug", sa.String(32), nullable=False),
        sa.Column(
            "external_account_id",
            sa.String(255),
            nullable=True,
            comment="The platform's account identifier — e.g. Meta ad account id.",
        ),
        sa.Column(
            "external_account_name",
            sa.String(255),
            nullable=True,
            comment="Human-readable account name from the platform.",
        ),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="DISCONNECTED",
        ),
        sa.Column(
            "scopes_granted",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Surfaced to the founder when state=ERROR. Never contains tokens.",
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
    # State enum CHECK — belt-and-braces with the Pydantic Literal.
    quoted = ", ".join(f"'{s}'" for s in _CONNECTION_STATES)
    op.execute(
        "ALTER TABLE integration_connection "
        f"ADD CONSTRAINT ck_integration_connection_state "
        f"CHECK (state IN ({quoted}))"
    )

    # Brand-id consistency: brand must belong to organization. We can't
    # FK-enforce this without a composite FK, but the service-layer
    # invariant is tested. Index for the hot lookup path.
    op.create_index(
        "ix_integration_connection_brand_org",
        "integration_connection",
        ["organization_id", "brand_id"],
    )

    # Partial unique: at most ONE non-terminal connection per
    # (org, brand, provider). Brand nullable → COALESCE the index key
    # to a sentinel zero-UUID so brand-NULL rows collide cleanly.
    op.execute(
        "CREATE UNIQUE INDEX ix_integration_connection_one_active "
        "ON integration_connection ("
        "organization_id, "
        "COALESCE(brand_id, '00000000-0000-0000-0000-000000000000'::uuid), "
        "provider_slug"
        ") "
        "WHERE state IN ('PENDING_AUTH', 'ACTIVE', 'EXPIRED', 'ERROR', 'SUSPENDED')"
    )

    # Lookup by provider_slug for the "list all my connections per
    # provider" path on /integrations.
    op.create_index(
        "ix_integration_connection_provider",
        "integration_connection",
        ["provider_slug", "state"],
    )

    # -----------------------------------------------------------------
    # 2. integration_credential — encrypted, never API-exposed
    # -----------------------------------------------------------------
    op.create_table(
        "integration_credential",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "integration_connection.id", ondelete="CASCADE"
            ),
            nullable=False,
            unique=True,  # 1:1 with the public row
        ),
        sa.Column(
            "encrypted_access_token",
            postgresql.BYTEA,
            nullable=False,
            comment="Fernet ciphertext. Decrypt via aicmo.modules.integrations.crypto.",
        ),
        sa.Column(
            "encrypted_refresh_token",
            postgresql.BYTEA,
            nullable=True,
        ),
        sa.Column(
            "token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "encrypted_raw_response",
            postgresql.BYTEA,
            nullable=True,
            comment="Optional full token blob — debug only, encrypted same as access_token.",
        ),
        sa.Column(
            "rotated_at",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("integration_credential")
    op.execute("DROP INDEX IF EXISTS ix_integration_connection_provider")
    op.execute("DROP INDEX IF EXISTS ix_integration_connection_one_active")
    op.drop_index(
        "ix_integration_connection_brand_org",
        table_name="integration_connection",
    )
    op.execute(
        "ALTER TABLE integration_connection "
        "DROP CONSTRAINT IF EXISTS ck_integration_connection_state"
    )
    op.drop_table("integration_connection")
