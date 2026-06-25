from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class Bundle(Base, TimestampMixin, TenantMixin):
    """One coordinated multi-asset campaign package.

    `pieces` is a list of {kind, id, label, platform, subtype, is_error,
    error_message} dicts pointing at rows in the asset-specific tables.
    Storing the references in JSONB (rather than four FK columns + a join
    table) keeps the schema flat and matches the polymorphic-attribution
    pattern already used by `leads.source_asset_*`.
    """

    __tablename__ = "bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    landing_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("landing_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    theme: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(String(32))
    duration_days: Mapped[int] = mapped_column(Integer, default=14)

    pieces: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
