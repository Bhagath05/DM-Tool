"""Creative Platform core ORM — media-agnostic (Creative Core V0).

Mirrors migration 0034 column-for-column; WHY lives in the migration.
Thin models, no relationship() joins (queried explicitly by brand_id —
same boundary rule as billing/security/team).

`creative_asset` is the UNIFIED ASSET LIBRARY: one row per deliverable of
ANY media type, with a polymorphic `source_kind`/`source_id` pointer to
the native render row (video_render / rendered_visual / generated_content)
and a `StorageRef` (storage_backend + storage_key) — never bytes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class CreativeFormat(Base):
    """Non-tenant catalog (like `plan`) — excluded from RLS."""

    __tablename__ = "creative_format"

    slug: Mapped[str] = mapped_column(String(48), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(32))
    aspect_ratio: Mapped[str] = mapped_column(String(8))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    max_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seeding: Mapped[str] = mapped_column(String(16), server_default="optional")
    style_preset: Mapped[str | None] = mapped_column(String(48), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreativeProject(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_project"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_profile_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # DB enforces the FK to campaign_plans (migration 0034). The ORM keeps a
    # plain UUID — no cross-module ORM FK (same boundary rule as billing) so
    # the model resolves without importing the campaigns module.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    creative_type: Mapped[str] = mapped_column(String(32))
    media_type: Mapped[str] = mapped_column(String(16))
    format_slug: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("creative_format.slug", ondelete="RESTRICT"), nullable=True
    )
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    objective: Mapped[str | None] = mapped_column(String(64), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_mode: Mapped[str] = mapped_column(String(16), server_default="tts_voiceover")
    status: Mapped[str] = mapped_column(String(32), server_default="draft")
    script: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    seed_asset_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    ab_group_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    estimated_cost_cents: Mapped[int] = mapped_column(Integer, server_default="0")
    actual_cost_cents: Mapped[int] = mapped_column(Integer, server_default="0")


class CreativeAsset(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_asset"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creative_project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_project.id", ondelete="CASCADE")
    )
    variant_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_type: Mapped[str] = mapped_column(String(16))
    creative_type: Mapped[str] = mapped_column(String(32))
    source_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    poster_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    caption_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(8), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="assembling")
    published_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CreativeVariant(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_variant"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creative_project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_project.id", ondelete="CASCADE")
    )
    ab_group_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    creative_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_asset.id", ondelete="SET NULL"), nullable=True
    )
    variant_label: Mapped[str] = mapped_column(String(16))
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    variable_changed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_control: Mapped[bool] = mapped_column(Boolean, server_default="false")
    performance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CreativeCostEvent(Base, TenantMixin):
    """Append-only cost ledger (what WE pay providers). No TimestampMixin —
    `occurred_at` is the only time we care about."""

    __tablename__ = "creative_cost_event"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creative_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_project.id", ondelete="SET NULL"), nullable=True
    )
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stage: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    units: Mapped[float] = mapped_column(Numeric(12, 3), server_default="0")
    unit_cost_cents: Mapped[float] = mapped_column(Numeric(12, 4), server_default="0")
    cost_cents: Mapped[int] = mapped_column(Integer, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandKit(Base, TimestampMixin, TenantMixin):
    __tablename__ = "brand_kit"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    logo_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    watermark_position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    color_primary: Mapped[str | None] = mapped_column(String(16), nullable=True)
    color_secondary: Mapped[str | None] = mapped_column(String(16), nullable=True)
    color_accent: Mapped[str | None] = mapped_column(String(16), nullable=True)
    font_heading: Mapped[str | None] = mapped_column(String(64), nullable=True)
    font_body: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intro_template_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    outro_template_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    end_card_cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    music_mood: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_zones: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false")


class CreativeTemplate(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_template"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    media_type: Mapped[str] = mapped_column(String(16))
    creative_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class CreativeExport(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_export"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creative_asset_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_asset.id", ondelete="CASCADE")
    )
    target_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    format_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
