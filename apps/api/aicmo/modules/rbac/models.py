from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TimestampMixin


class Role(Base, TimestampMixin):
    """A role bundles permissions. Two kinds:

    - System roles: `organization_id IS NULL`, `is_system = TRUE`,
      shared across all orgs. Owner / Admin / Editor / Viewer.
    - Custom roles: `organization_id` set, per-org definitions. Not
      exposed in S1.0 — the schema supports it for Tier 4 builder UI.

    Slug uniqueness is enforced by two partial unique indices in
    migration 0014 (one for system slugs globally, one for custom
    slugs per org).
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class Permission(Base):
    """One permission slug. No TimestampMixin — permissions are
    effectively immutable seed data; updated_at would be misleading.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_permissions_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RolePermission(Base):
    """Many-to-many. Composite primary key on (role_id, permission_id)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
