"""RenderedVisual ORM — Phase 4-A.

Kept in a separate file (not models.py) to make the additive nature
obvious and rollback trivial. One table, no FK touch to existing rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class RenderedVisual(Base, TimestampMixin, TenantMixin):
    """One physical render of a `GeneratedVisual` brief.

    A brief can have many renders (variations + regenerations). Each row
    points at a single file on disk (or — later — an S3 key); the file
    name is derived from `id` so we never need a separate path column
    in the typical path. We keep `file_path` explicit anyway for the
    case where MEDIA_DIR is reconfigured between runs.

    `prompt_fingerprint` is a SHA-256 hash of the final prompt sent to
    the provider. Lets us detect "user clicked regenerate but nothing
    changed" and short-circuit if we ever want to cache. Not used yet.
    """

    __tablename__ = "rendered_visuals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    visual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_visuals.id", ondelete="CASCADE"),
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(32))  # 'openai', etc.
    provider_image_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    # Final natural-language prompt we sent the provider. Stored for audit
    # and so the frontend can render a "see what we asked the AI" panel.
    prompt: Mapped[str] = mapped_column(Text)
    prompt_fingerprint: Mapped[str] = mapped_column(String(64), index=True)

    file_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(32), default="image/png")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Carousel slides share one visual_id; slide_index orders them (0-based).
    slide_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
