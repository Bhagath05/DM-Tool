from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class GeneratedContent(Base, TimestampMixin, TenantMixin):
    """One row per generation. Saved or not, the row is kept until the user
    explicitly deletes it. `is_saved` is a 'favourite' flag for filtering."""

    __tablename__ = "generated_content"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    # Nullable: a user can generate before they ever refreshed trends.
    trend_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trend_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Attribution — if the user attaches this asset to a landing page,
    # leads captured through that page get linked back via source_asset_*.
    landing_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("landing_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Phase 6.2 — full asset traceability. All nullable + SET NULL: the content
    # is valuable in its own right, so deleting a campaign/bundle/strategy/
    # recommendation must NOT delete the asset, only unlink it. Ownership of each
    # is validated against the tenant's brand before persisting.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bundles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketing_strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advisor_recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    content_type: Mapped[str] = mapped_column(String(32))  # social_post|reel|carousel|ad_copy
    platform: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(String(255))
    tone: Mapped[str] = mapped_column(String(64))

    # Why-it-works metadata (ContentStrategy schema).
    strategy: Mapped[dict] = mapped_column(JSONB)
    # Type-specific output. Schema depends on content_type.
    output: Mapped[dict] = mapped_column(JSONB)

    # Phase 9.1 — Performance Intelligence tags. See generated_visuals
    # for the rationale; same columns, same nullable contract.
    concept_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(96), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_goal: Mapped[str | None] = mapped_column(String(96), nullable=True)
    offer_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Phase 6.2B — enterprise content ops.
    # Approval workflow: draft → in_review → changes_requested | approved |
    # rejected → published → archived. History lives in content_review_events.
    review_status: Mapped[str] = mapped_column(
        String(24), default="draft", server_default="draft", index=True
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
