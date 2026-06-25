from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    """Top-level tenant. Owns billing + team. Holds N brands.

    `member_count` and `brand_count` are denormalised for fast UI reads
    (avoiding a COUNT(*) on the dashboard for every customer). Services
    that mutate membership/brands update these counters in the same txn.
    """

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_organizations_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_organizations_owner"),
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    member_count: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    brand_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    # ----- Phase 10.2f — profile metadata ----------------------------
    # All nullable. Filled in via Settings → Organization. CHECK on
    # `country` enforces ISO-3166 alpha-2 format at the DB layer; full
    # IANA validation for `timezone` happens in Pydantic.
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)


class OrganizationMember(Base, TimestampMixin):
    """User's active membership in an organization.

    One row per (org, user) — partial unique index on the DB side
    enforces no double-active-membership. `last_active_brand_id` is the
    sticky brand selection so a returning user lands back on the brand
    they were working on.
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'removed')",
            name="ck_org_members_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_active_brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )


class MemberRole(Base):
    """Member ↔ role assignment. No TimestampMixin — `assigned_at` is
    the only time we care about here, and a role assignment isn't
    "updated" — it's added or removed.
    """

    __tablename__ = "member_roles"
    __table_args__ = (
        UniqueConstraint(
            "member_id", "role_id", name="uq_member_roles_member_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_members.id", ondelete="CASCADE"),
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
