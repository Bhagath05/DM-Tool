"""Creative Studio design ORM — editable design + immutable revisions.

Mirrors migration 0035 column-for-column; WHY lives in the migration.
Thin models, no relationship() joins.

Boundary rule (same as billing/creative core): cross-module references
(creative_project, creative_format, growth_objective) are PLAIN columns —
the DB keeps the real FK from the migration, but the ORM carries no
cross-module ForeignKey so these models resolve without importing the
campaigns/growth/creative-core mappers. Intra-module references
(design_id, parent_revision_id) keep their ORM FK.

`head_revision_id` is a plain UUID (no DB FK either) to avoid a circular
FK with creative_design_revision; integrity is maintained by apply_revision.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class CreativeDesign(Base, TimestampMixin, TenantMixin):
    """The editable layer-document head. `doc` is a denormalized cache of
    the head revision; `current_revision` is the optimistic lock."""

    __tablename__ = "creative_design"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Cross-module — plain UUID/str, DB keeps the FK (boundary rule).
    creative_project_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    growth_objective_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    format_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    media_type: Mapped[str] = mapped_column(String(16))
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    current_revision: Mapped[int] = mapped_column(Integer, server_default="0")
    head_revision_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    default_mode: Mapped[str] = mapped_column(String(8), server_default="ai")  # ai|guided|pro (UI default only)
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class CreativeDesignRevision(Base, TenantMixin):
    """Immutable, append-only snapshot — the Human+AI collaboration backbone
    (Law 3). Never UPDATEd/DELETEd in app code. The single writer is
    apply_revision(). No TimestampMixin — a snapshot has only created_at."""

    __tablename__ = "creative_design_revision"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("creative_design.id", ondelete="CASCADE")
    )
    revision_n: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("creative_design_revision.id", ondelete="SET NULL"),
        nullable=True,
    )
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ops: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(24))      # ai_generate|ai_edit|ai_regenerate|ai_restyle|ai_transform|user_edit|template
    actor_kind: Mapped[str] = mapped_column(String(8))   # ai|human
    mode: Mapped[str] = mapped_column(String(8))         # ai|guided|pro
    review_status: Mapped[str] = mapped_column(String(20), server_default="draft")
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Immutable: only created_at matters (no updated_at semantics for a snapshot).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandAsset(Base, TimestampMixin, TenantMixin):
    """Tenant-owned uploaded assets the layer doc references by id
    (logo/font/image/color/icon). Stores a StorageRef, never bytes."""

    __tablename__ = "brand_asset"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # logo|font|image|color|icon
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    is_favorite: Mapped[bool] = mapped_column(Boolean, server_default="false")
