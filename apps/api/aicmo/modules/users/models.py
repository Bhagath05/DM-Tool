from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Mirror of Clerk identity. One row per signed-up human.

    Lazy-created on first authenticated request (see users.service.
    get_or_create_from_clerk) AND via the Clerk webhook (when wired in a
    later slice). Both paths converge on the same row keyed by
    clerk_user_id.

    `email` is mirrored from Clerk so we can drive invites and team
    listings without round-tripping. It's kept in sync via the webhook;
    not authoritative.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="ck_users_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Legacy Clerk `sub` claim. Retained (nullable) across the first-party auth
    # migration so historical rows and any external references survive; new
    # first-party accounts leave it NULL. No longer the authentication key.
    clerk_user_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    # CITEXT in the DB (case-insensitive). SQLAlchemy treats as plain str.
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # First-party authentication. `password_hash` is an Argon2id PHC string
    # (never plaintext, never reversible); NULL means the account has no DM Tool
    # password yet. `email_verified_at` gates sign-in; `password_changed_at`
    # supports "sessions invalidated after a password change" auditing.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
