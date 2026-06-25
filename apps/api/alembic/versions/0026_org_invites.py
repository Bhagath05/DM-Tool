"""organization invites — phase 10.2d

Revision ID: 0026_org_invites
Revises: 0025_analyst_role
Create Date: 2026-06-05

Phase 10.2d — Per-org invite table.

Design notes:

- Token storage. We NEVER store raw invite tokens. The `token_hash`
  column holds `sha256(raw_token)` as a hex string; the raw token is
  returned to the caller ONCE at creation time (encoded in the invite
  URL) and lost forever from our side. An attacker reading the DB can't
  forge an acceptance — they'd still need to brute the preimage.

- Email storage. We lowercase + trim before insert; the partial unique
  index on `(organization_id, lower(email))` WHERE status='pending'
  prevents accidentally inviting the same address twice into the same
  org while the first invite is still open. Re-inviting after a
  revoke / expire / accept is fine — those are terminal statuses.

- Status enum (CHECK):
    pending   — invite URL exists, not yet used
    accepted  — used; member row + role assignment created
    revoked   — explicitly cancelled by admin/owner
    expired   — past expires_at, never accepted

  Transitions are one-way: pending → {accepted | revoked | expired}.
  No invite ever returns to pending. This means we can scan the
  partial index for "pending with this email" without joining.

- Role slug stored as a string, not FK. The role catalog is static
  (system roles), and storing the slug means we don't need to look up
  the role row at accept-time to render the invite preview. The
  service layer validates against the canonical 4-role catalog on
  CREATE.

- `accepted_by_user_id` may differ from invitee's email-derived user
  if Clerk identifier changes; we record the user id at acceptance
  so the audit trail is complete.

Rollback drops the table. No data lost beyond pending invites —
already-accepted invitations are realised as member + member_role rows
in the existing tables, untouched by this migration.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0026_org_invites"
down_revision: Union[str, None] = "0025_analyst_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Lock-step with aicmo/modules/team/schemas.py and the role catalog.
_STATUSES = ("pending", "accepted", "revoked", "expired")
_INVITABLE_ROLES = ("admin", "analyst", "editor", "viewer")
# Note: 'owner' is deliberately NOT in the CHECK list — you cannot
# invite as owner. Ownership is conferred at workspace creation or via
# the (future) transfer-ownership flow, never via invite.


def upgrade() -> None:
    op.create_table(
        "organization_invite",
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
            "email",
            sa.String(255),
            nullable=False,
            comment="Lowercased + trimmed by the service layer before insert.",
        ),
        sa.Column(
            "role_slug",
            sa.String(64),
            nullable=False,
            comment="System role to grant on accept. CHECK enforced.",
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment=(
                "SET NULL on cascade — inviter may be removed before the "
                "invite is consumed; we still want the invite to work."
            ),
        ),
        sa.Column(
            "token_hash",
            sa.String(64),
            nullable=False,
            unique=True,
            comment=(
                "sha256(raw_token) hex. Raw token is returned to the caller "
                "ONCE at creation and never persisted. UNIQUE so a brute "
                "lookup can't accidentally collide."
            ),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Past this point, accept returns 410 Gone and status → expired.",
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "accepted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_by_user_id",
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

    # Status CHECK.
    quoted_statuses = ", ".join(f"'{s}'" for s in _STATUSES)
    op.execute(
        "ALTER TABLE organization_invite "
        "ADD CONSTRAINT ck_org_invite_status "
        f"CHECK (status IN ({quoted_statuses}))"
    )

    # Role-slug CHECK — 'owner' deliberately absent.
    quoted_roles = ", ".join(f"'{r}'" for r in _INVITABLE_ROLES)
    op.execute(
        "ALTER TABLE organization_invite "
        "ADD CONSTRAINT ck_org_invite_role_slug "
        f"CHECK (role_slug IN ({quoted_roles}))"
    )

    # Status-pair invariants. If status=accepted, accepted_at + by must
    # be set; if status=revoked, revoked_at + by must be set. Prevents
    # a buggy write from leaving the audit trail incomplete.
    op.execute(
        "ALTER TABLE organization_invite "
        "ADD CONSTRAINT ck_org_invite_accept_pair "
        "CHECK ((status = 'accepted') = (accepted_at IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE organization_invite "
        "ADD CONSTRAINT ck_org_invite_revoke_pair "
        "CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))"
    )

    # Lookup by token_hash on accept — UNIQUE column already gives us the
    # index, but make it explicit for grep.
    op.create_index(
        "ix_org_invite_token_hash",
        "organization_invite",
        ["token_hash"],
        unique=True,
        if_not_exists=True,
    )

    # Prevent two simultaneous pending invites to the same email/org.
    # Partial: terminal-status rows don't block re-invites.
    op.execute(
        "CREATE UNIQUE INDEX uq_org_invite_one_pending_per_email "
        "ON organization_invite (organization_id, lower(email)) "
        "WHERE status = 'pending'"
    )

    # Hot path: list pending invites for an org (Settings → Team).
    op.create_index(
        "ix_org_invite_org_status",
        "organization_invite",
        ["organization_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_invite_org_status", table_name="organization_invite")
    op.execute("DROP INDEX IF EXISTS uq_org_invite_one_pending_per_email")
    op.execute("DROP INDEX IF EXISTS ix_org_invite_token_hash")
    op.execute(
        "ALTER TABLE organization_invite "
        "DROP CONSTRAINT IF EXISTS ck_org_invite_revoke_pair"
    )
    op.execute(
        "ALTER TABLE organization_invite "
        "DROP CONSTRAINT IF EXISTS ck_org_invite_accept_pair"
    )
    op.execute(
        "ALTER TABLE organization_invite "
        "DROP CONSTRAINT IF EXISTS ck_org_invite_role_slug"
    )
    op.execute(
        "ALTER TABLE organization_invite "
        "DROP CONSTRAINT IF EXISTS ck_org_invite_status"
    )
    op.drop_table("organization_invite")
