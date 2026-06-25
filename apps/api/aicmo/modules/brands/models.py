from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TimestampMixin


class Brand(Base, TimestampMixin):
    """A brand under an organization. The actual tenant boundary for
    every business row.

    Slug is unique per org (not globally) and only among non-deleted
    brands — see migration 0013 for the partial unique index.
    """

    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_brands_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
    )
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_brands_created_by"),
    )

    # ----- Phase 10.2f — profile metadata + default flag -------------
    # `active` is intentionally NOT stored — derived via `is_active`
    # property from `status`, so the dozen+ services that already filter
    # on `status = 'active'` stay the single source of truth.
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    @property
    def is_active(self) -> bool:
        """Single source of truth for 'is this brand usable?' —
        derived from the existing `status` column."""
        return self.status == "active"
