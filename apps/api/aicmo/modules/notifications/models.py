"""Phase 10.2b — ORM for notification_preference.

One row per explicit toggle. The composite primary key
(user_id, organization_id, category, channel) makes this trivially
upsertable via ON CONFLICT — no surrogate id, no extra unique index.

Defaults are NOT stored. A user with all-defaults has zero rows; the
service layer materialises the 18-cell matrix by overlaying stored
rows on `catalog.default_for(category, channel)`. This means:
  - Storage scales with diverged-from-default cells, not user count.
  - Adding a new category/channel needs no backfill.
  - "Reset to defaults" is just `DELETE WHERE user_id=? AND org_id=?`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="user"
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

    def __repr__(self) -> str:
        return (
            f"<NotificationPreference user={self.user_id} org={self.organization_id} "
            f"{self.category}/{self.channel}={self.enabled}>"
        )
