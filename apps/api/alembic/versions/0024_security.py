"""security backend — phase 10.2c

Revision ID: 0024_security
Revises: 0023_notifications
Create Date: 2026-06-05

Phase 10.2c — Session inventory + security event audit trail.

Two tables, each with a single responsibility:

  user_session
    Mirror of a Clerk session. Clerk remains the source of truth for
    authentication; this row exists so the founder can see + revoke
    their active devices, and so we can correlate security events back
    to a specific session. `clerk_session_id` is the external reference
    — we never mint our own session ids.

  security_event
    Append-only audit log. Six event types:
      login, logout, failed_login, password_change, mfa_challenge, session_revoke
    `user_id` is NULLABLE because a failed login may not resolve to a
    user we know (and that's exactly the case we want to log).

Hot indexes are chosen for the Settings → Security page's three jobs:
  1. "list my sessions"             → ix_user_session_user_recent
  2. "list my recent events"        → ix_security_event_user_recent
  3. "lookup by clerk session id"   → ix_security_event_session
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0024_security"
down_revision: Union[str, None] = "0023_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept in lock-step with aicmo/modules/security/schemas.py.
_EVENT_TYPES = (
    "login",
    "logout",
    "failed_login",
    "password_change",
    "mfa_challenge",
    "session_revoke",
)

_ACTORS = (
    "self",     # the user themselves (most common)
    "admin",    # an org admin acting on behalf of the user
    "system",   # automated — clerk webhook, expiry, etc.
    "unknown",  # failed_login from an unverified email, etc.
)

_REVOKED_BY = (
    "user",     # user clicked "revoke this device"
    "admin",    # org admin revoked the session
    "webhook",  # Clerk webhook delivered session.revoked
    "system",   # expired / superseded / forced
)


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. user_session — device + session inventory
    # -----------------------------------------------------------------
    op.create_table(
        "user_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clerk_session_id",
            sa.String(128),
            nullable=False,
            unique=True,
            comment="External reference. Clerk owns session lifecycle; we mirror.",
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
            comment="Raw User-Agent string at session creation. Parsed on read.",
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "geo_country",
            sa.String(2),
            nullable=True,
            comment="ISO-3166 alpha-2. Populated by edge geolocation if available.",
        ),
        sa.Column(
            "geo_city",
            sa.String(128),
            nullable=True,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="From Clerk session payload — surfaced to UI as 'expires in X'.",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_by",
            sa.String(16),
            nullable=True,
            comment="user/admin/webhook/system — non-null iff revoked_at non-null.",
        ),
        sa.Column(
            "revocation_status",
            sa.String(32),
            nullable=True,
            comment=(
                "Best-effort outcome of the Clerk-side revoke call. "
                "'remote_ok' = Clerk acknowledged revocation. "
                "'local_only' = our row marked revoked, Clerk call skipped "
                "(no secret configured) or failed."
            ),
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
    quoted_revokers = ", ".join(f"'{r}'" for r in _REVOKED_BY)
    op.execute(
        "ALTER TABLE user_session "
        "ADD CONSTRAINT ck_user_session_revoked_by "
        f"CHECK (revoked_by IS NULL OR revoked_by IN ({quoted_revokers}))"
    )
    # If revoked_at is set, revoked_by MUST be set too (paired columns).
    op.execute(
        "ALTER TABLE user_session "
        "ADD CONSTRAINT ck_user_session_revoke_pair "
        "CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))"
    )
    # Hot path: "load my active sessions, newest first" — most recent
    # last_seen wins. Partial index on non-revoked rows keeps it tight.
    op.create_index(
        "ix_user_session_user_recent",
        "user_session",
        ["user_id", sa.text("last_seen_at DESC")],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # -----------------------------------------------------------------
    # 2. security_event — append-only audit log
    # -----------------------------------------------------------------
    op.create_table(
        "security_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # user_id NULLABLE — a failed_login from an unknown email won't
        # resolve to a user row. We still want to log it.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # org_id NULLABLE — login events aren't org-scoped (a user signs
        # in once, then chooses an org). Session revoke triggered by an
        # org admin IS org-scoped, so we keep the column available.
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "clerk_session_id",
            sa.String(128),
            nullable=True,
            comment="When applicable — string FK, no constraint (Clerk owns).",
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(16), nullable=False, server_default="self"),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Small bag for event-specific extras: mfa method, fail "
                "reason, geo at time of event. MUST NOT contain tokens, "
                "passwords, or PII beyond what we'd surface back to the user."
            ),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the event actually happened (from webhook payload if available).",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When our row was inserted. Differs from occurred_at on replay.",
        ),
    )
    quoted_events = ", ".join(f"'{e}'" for e in _EVENT_TYPES)
    op.execute(
        "ALTER TABLE security_event "
        "ADD CONSTRAINT ck_security_event_type "
        f"CHECK (event_type IN ({quoted_events}))"
    )
    quoted_actors = ", ".join(f"'{a}'" for a in _ACTORS)
    op.execute(
        "ALTER TABLE security_event "
        "ADD CONSTRAINT ck_security_event_actor "
        f"CHECK (actor IN ({quoted_actors}))"
    )

    # Hot path 1: "show my last N security events on the settings page"
    op.create_index(
        "ix_security_event_user_recent",
        "security_event",
        ["user_id", sa.text("occurred_at DESC")],
    )
    # Hot path 2: lookup by clerk session — correlate events to a device row
    op.create_index(
        "ix_security_event_session",
        "security_event",
        ["clerk_session_id"],
        postgresql_where=sa.text("clerk_session_id IS NOT NULL"),
    )
    # Hot path 3: org-scoped "show me security events across my workspace"
    # (Phase 10.2d admin views). Cheap to add now.
    op.create_index(
        "ix_security_event_org_recent",
        "security_event",
        ["organization_id", sa.text("occurred_at DESC")],
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_security_event_org_recent", table_name="security_event"
    )
    op.drop_index("ix_security_event_session", table_name="security_event")
    op.drop_index(
        "ix_security_event_user_recent", table_name="security_event"
    )
    op.execute(
        "ALTER TABLE security_event "
        "DROP CONSTRAINT IF EXISTS ck_security_event_actor"
    )
    op.execute(
        "ALTER TABLE security_event "
        "DROP CONSTRAINT IF EXISTS ck_security_event_type"
    )
    op.drop_table("security_event")

    op.drop_index("ix_user_session_user_recent", table_name="user_session")
    op.execute(
        "ALTER TABLE user_session "
        "DROP CONSTRAINT IF EXISTS ck_user_session_revoke_pair"
    )
    op.execute(
        "ALTER TABLE user_session "
        "DROP CONSTRAINT IF EXISTS ck_user_session_revoked_by"
    )
    op.drop_table("user_session")
