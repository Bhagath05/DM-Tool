"""First-party authentication tables.

Companion to the `users` row (which gains `password_hash` / `email_verified_at`
/ `password_changed_at` — see the users model). These three tables hold the
server-side session store, the single-use email/reset tokens, and the login
throttling ledger. In every case we persist only a SHA-256 *hash* of any secret
— never the raw session token or the raw email/reset token.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TimestampMixin


class UserSession(Base, TimestampMixin):
    """One server-side session. The browser holds the raw token in an HttpOnly
    cookie; we store only its SHA-256 hash. A session is valid iff it exists,
    is not revoked, and has not expired."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # SHA-256 hex of the raw session token. Unique so a lookup is O(1) and a
    # token collision is impossible in practice.
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when the session is explicitly ended (logout, password change,
    # revoke-all). A non-null value means "no longer valid", independent of
    # expiry.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmailToken(Base, TimestampMixin):
    """A single-use, hashed, expiring token backing email verification and
    password reset. The raw token travels only inside the emailed link; we keep
    the SHA-256 hash. `used_at` enforces single-use; `expires_at` enforces TTL."""

    __tablename__ = "email_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('verify', 'reset')", name="ck_email_tokens_purpose"),
        Index("ix_email_tokens_user_purpose", "user_id", "purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailSuppression(Base, TimestampMixin):
    """A permanently-undeliverable auth email DESTINATION.

    Written only on a terminal recipient rejection (the mailbox itself is bad),
    never on transient failures or on our-side SMTP/config problems. The auth
    delivery path checks this table (by the user's CURRENT normalized email)
    before sending and skips a suppressed address — so an old suppressed address
    can never block a new one after an email change (the identity is the email,
    not the user). Holds NO token, URL, or SMTP credential.

    `email` is the normalized (lowercased) destination and is the unique
    idempotency key: repeated permanent failures upsert the same row. `user_id`
    is a best-effort reference (SET NULL on user delete) so a future MTA
    bounce/DSN for an address without a known user can reuse the same table.
    """

    __tablename__ = "email_suppressions"
    __table_args__ = (
        UniqueConstraint("email", name="uq_email_suppressions_email"),
        Index("ix_email_suppressions_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Normalized (lowercased) destination address — the suppression identity.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    # Why the address is suppressed (e.g. "permanent_bounce"). Free-form so a
    # future MTA bounce pipeline can add its own reasons; never a secret.
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    # Which subsystem recorded it (e.g. "auth_email_delivery", later "mta_dsn").
    source: Mapped[str] = mapped_column(String(48), nullable=False)
    # Optional non-sensitive metadata for future bounce handling (e.g. a DSN
    # status code). NEVER a token, link, email body, or credential.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class LoginAttempt(Base):
    """Append-only ledger of authentication attempts, used to throttle
    brute-force / credential-stuffing by both account (email) and source IP.

    Stores the *attempted* email (lowercased) — not a user id — so attempts
    against non-existent accounts are still counted without leaking existence.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_email_time", "email", "created_at"),
        Index("ix_login_attempts_ip_time", "ip", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
