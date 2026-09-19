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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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
