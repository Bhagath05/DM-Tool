import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base. Import every ORM model here so Alembic can see them."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Multi-tenant scoping. Every business table inherits this so its
    rows are reachable only through (organization_id, brand_id).

    Columns are added by migration 0015 (nullable) → 0016 (backfill) →
    0017 (NOT NULL flip). After 0017, the ORM declares them NOT NULL.

    Service-layer queries MUST filter on brand_id. The companion guard
    in tenancy/guards.py is a defence-in-depth check.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


# Model registration happens in the entry points (aicmo/main.py for the
# runtime, alembic/env.py for migrations) — importing models here would
# create a circular dependency since models.py imports Base.
