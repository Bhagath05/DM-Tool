from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class SocialConnection(Base, TimestampMixin, TenantMixin):
    """One row per (user, platform). Holds OAuth credentials + the metadata
    the provider needs to call its API on behalf of this user.

    `metadata_json` is intentionally loose — every platform returns a
    different shape (Instagram → `business_account_id`, LinkedIn → `urn`,
    YouTube → `channel_id`). We keep raw + a few extracted convenience
    fields rather than 4× per-platform tables.
    """

    __tablename__ = "social_connections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", name="uq_social_connection_user_platform"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str] = mapped_column(
        String(32), index=True
    )  # instagram | facebook | linkedin | youtube | tiktok

    # OAuth bits. `access_token` is encrypted-at-rest in prod TODO; for MVP
    # it sits in JSONB so we can rotate the storage shape without a migration.
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Free-form per-platform metadata: handles, IDs, account types, etc.
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # How we got the data:
    #   "oauth" → real Graph/LinkedIn/etc connection
    #   "manual_import" → user pasted JSON, no live token (testable today)
    source: Mapped[str] = mapped_column(
        String(16), default="oauth", server_default="oauth"
    )

    # Last successful sync, for the dashboard's "refreshed N min ago" badge.
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SocialAsset(Base, TimestampMixin, TenantMixin):
    """One row per ingested post / video / story. Same row carries:
    - the normalized fields we query on
    - the FULL raw payload from the provider in `raw_json` so we never
      lose data we might want to mine later (per "don't over-normalize")
    """

    __tablename__ = "social_assets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "platform_post_id",
            name="uq_social_asset_post",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("social_connections.id", ondelete="CASCADE"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)

    # Provider's stable id for the post / video.
    platform_post_id: Mapped[str] = mapped_column(String(128))
    # post | reel | story | short | video | image | carousel | live
    asset_type: Mapped[str] = mapped_column(String(32), index=True)

    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Loose store for everything the provider returned that we didn't pull
    # out into typed columns. Future analytics will mine this.
    raw_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )


class PerformanceSignal(Base, TimestampMixin):
    """Per-asset performance snapshot. One row per (asset, captured_at).

    Why a separate table from SocialAsset: a single post's metrics change
    daily, and we want a TIME SERIES not just the latest snapshot. For
    MVP we only insert one row per asset (latest); the design allows
    multiple rows per asset later.
    """

    __tablename__ = "performance_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("social_assets.id", ondelete="CASCADE"),
        index=True,
    )

    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    # Stored as decimal fraction (0.045 = 4.5%) so we can sort + aggregate.
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Video-only:
    views: Mapped[int] = mapped_column(Integer, default=0)
    watch_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)

    raw_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )


class AudiencePattern(Base, TimestampMixin, TenantMixin):
    """Per-user, per-platform observation about WHO is engaging.

    Example pattern_type values:
    - "demographic_skew" — "audience leans female 25-34"
    - "geographic_concentration" — "60% of engagement is Hyderabad"
    - "active_time" — "9pm IST drives 2x engagement vs 3pm"
    - "interest_overlap" — "top followers also follow indie coffee creators"

    We keep this loose intentionally — patterns are LLM-derived strings.
    """

    __tablename__ = "audience_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)

    pattern_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.5
    )  # 0.00 – 1.00


class WinningPattern(Base, TimestampMixin, TenantMixin):
    """The most important table in the module.

    These rows are what the GenerationContext inherits and what every
    generator now sees automatically. If we got this table right, the
    next ad/reel/post should sound less generic — because the LLM was
    told "founder-led hooks with warm dark visuals outperform product
    showcases for this business" before it wrote a word.
    """

    __tablename__ = "winning_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )  # nullable so cross-platform patterns are allowed

    # Each of these is optional — a pattern may speak to only one dimension.
    # The analyzer fills the relevant ones and leaves the rest null.
    hook_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    posting_time_pattern: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # The one-line summary the generator inherits, e.g. "Founder-led short
    # reels with warm dark visuals outperform product showcases 2.4x".
    summary: Mapped[str] = mapped_column(Text)

    # 0.0 – 1.0. Computed from the sample size + effect-size of the
    # underlying engagement gap. The analyzer prompt sets it.
    performance_score: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.5
    )

    # Which assets fed this pattern — so the user can audit it. List of
    # SocialAsset UUIDs.
    source_asset_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
