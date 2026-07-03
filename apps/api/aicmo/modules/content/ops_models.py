"""Phase 6.2B — enterprise content-operations models.

Extends the existing `generated_content` asset with the ops layer marketing
teams need: immutable version history, threaded comments + mentions, folders/
collections, and an approval-workflow event log. All tenant-scoped (org + brand)
so reads never cross a tenant boundary. Nothing here duplicates the Creative
Studio's design-revision system (which versions visual DESIGNS, not text assets).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class ContentVersion(Base, TimestampMixin, TenantMixin):
    """Immutable snapshot of a generated_content asset at a point in time. One
    row per save (AI generation or manual edit). Append-only — never updated."""

    __tablename__ = "content_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_content.id", ondelete="CASCADE"),
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer)
    output: Mapped[dict] = mapped_column(JSONB)
    strategy: Mapped[dict] = mapped_column(JSONB, default=dict)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "ai" (generated/regenerated) | "manual" (human edit) | "restore".
    edit_source: Mapped[str] = mapped_column(
        String(16), default="ai", server_default="ai"
    )
    author_user_id: Mapped[str] = mapped_column(String(255))


class ContentFolder(Base, TimestampMixin, TenantMixin):
    """A folder or collection for organising assets. `parent_id` allows nesting."""

    __tablename__ = "content_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    # "folder" | "collection".
    kind: Mapped[str] = mapped_column(
        String(16), default="folder", server_default="folder"
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_by_user_id: Mapped[str] = mapped_column(String(255))


class ContentComment(Base, TimestampMixin, TenantMixin):
    """Threaded comment on an asset. `parent_id` threads replies; `mentions` is a
    list of mentioned user ids; `resolved` toggles the thread state."""

    __tablename__ = "content_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_content.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_user_id: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ContentReviewEvent(Base, TimestampMixin, TenantMixin):
    """One approval-workflow transition. The append-only history behind an
    asset's review_status."""

    __tablename__ = "content_review_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_content.id", ondelete="CASCADE"),
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[str] = mapped_column(String(255))
    # created_at (TimestampMixin) is the transition time.
