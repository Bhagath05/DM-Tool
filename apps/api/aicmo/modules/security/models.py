"""Phase 10.2c — ORM for user_session + security_event.

Both tables are write-mostly from the request path's perspective:
  - user_session: webhook INSERTs new sessions, the revoke endpoint
    UPDATEs revoked_at. Reads happen on the settings page.
  - security_event: every event is a single INSERT. Reads happen on
    the settings timeline + (later) on admin dashboards.

There's no relationship() declared between User and either of these
on purpose — they're queried by user_id directly, never via lazy
join, so a misconfigured `lazy="select"` can't accidentally fetch a
user's entire event log when loading a profile.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clerk_session_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    user_agent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET(), nullable=True)
    geo_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    geo_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    revocation_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return (
            f"<UserSession id={self.id} user={self.user_id} "
            f"clerk={self.clerk_session_id} active={self.is_active}>"
        )


class SecurityEvent(Base):
    __tablename__ = "security_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    clerk_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="self"
    )
    ip_address: Mapped[str | None] = mapped_column(INET(), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # map ORM attr → reserved-word-free DB column name
        JSONB(),
        nullable=False,
        server_default="{}",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityEvent id={self.id} user={self.user_id} "
            f"type={self.event_type} actor={self.actor}>"
        )
