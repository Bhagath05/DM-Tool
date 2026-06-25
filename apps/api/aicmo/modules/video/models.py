"""Video subsystem ORM — video-specific only (Creative Core V0).

The shared deliverable lives in `creative_asset`; these two tables are the
genuinely video-only pieces (storyboard scenes + per-clip Veo renders).
Mirrors migration 0034. `video_render` mirrors `rendered_visuals`
(provider/cost/latency/fingerprint) + video fields + async op id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class VideoScene(Base, TimestampMixin, TenantMixin):
    __tablename__ = "video_scene"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creative_project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_project.id", ondelete="CASCADE")
    )
    scene_index: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    motion_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_s: Mapped[Decimal] = mapped_column(Numeric(4, 1), server_default="8")
    seed_image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vo_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")


class VideoRender(Base, TimestampMixin, TenantMixin):
    __tablename__ = "video_render"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_scene_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("video_scene.id", ondelete="CASCADE")
    )
    creative_project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_project.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_operation_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    prompt_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(48), server_default="video/mp4")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_native_audio: Mapped[bool] = mapped_column(Boolean, server_default="false")
    synthid_watermark: Mapped[bool] = mapped_column(Boolean, server_default="false")
    status: Mapped[str] = mapped_column(String(16), server_default="submitted")
    error_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_cents: Mapped[int] = mapped_column(Integer, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, server_default="0")
