from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class Lead(Base, TimestampMixin, TenantMixin):
    """A captured lead — the unit of value this platform produces.

    Polymorphic attribution: `source_asset_type` + `source_asset_id` are
    plain string columns (no FK). Lets a lead point at any of
    campaign_plans / generated_ads / generated_content / generated_visuals
    without forcing 4 nullable FK columns. The trade-off — no referential
    integrity at write time — is acceptable because the source asset is
    purely informational; deleting the asset shouldn't cascade-delete a
    lead the customer has already captured.

    Storage of raw IPs forbidden by GDPR pragmatism: `ip_hash` is a
    SHA-256(pepper + ip) truncated to 32 chars. Lets us rate-limit and
    spot repeat submitters without holding PII.
    """

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_user_created", "user_id", "created_at"),
        Index("ix_leads_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )

    # Lead identity
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Any extra form fields beyond the canonical four go here.
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Attribution
    landing_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("landing_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_asset_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # UTM — the only marketing convention worth respecting upstream
    utm_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Request metadata
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Inbox state (the only "CRM" we ship in MVP)
    status: Mapped[str] = mapped_column(
        String(16), default="new", server_default="new"
    )  # new | hot | warm | cold | archived
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
