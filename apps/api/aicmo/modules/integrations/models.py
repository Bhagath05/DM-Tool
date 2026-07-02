"""ORM for the Phase 10.2a integration framework.

Two tables, separated by access surface:

  IntegrationConnection  — public metadata. Safe to expose via API.
  IntegrationCredential  — encrypted token blob. NEVER serialised.

A `service` function that needs the access token calls
`crypto.decrypt(connection.credential.encrypted_access_token, key)`
explicitly — there is no auto-decryption on attribute access. This
makes every callsite that touches secrets grep-able for audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aicmo.db.base import Base


class IntegrationConnection(Base):
    """Public metadata for an OAuth-or-API-key connection to a third-
    party platform. One row per (org, brand?, provider) — bounded by
    the partial unique index in migration 0022."""

    __tablename__ = "integration_connection"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=True,
    )
    provider_slug: Mapped[str] = mapped_column(String(32), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    external_account_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="DISCONNECTED"
    )
    scopes_granted: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    credential: Mapped[IntegrationCredential | None] = relationship(
        "IntegrationCredential",
        back_populates="connection",
        uselist=False,
        cascade="all, delete-orphan",
        # We intentionally do NOT eager-load. Callers must explicitly
        # opt-in via a selectinload(...) — keeps "I just want the
        # public metadata" queries free of secret-table joins.
        lazy="raise_on_sql",
    )


class IntegrationCredential(Base):
    """Encrypted OAuth tokens. Decrypt via
    `aicmo.modules.integrations.crypto.decrypt` only — there is no
    plain-text accessor on this model."""

    __tablename__ = "integration_credential"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connection.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    encrypted_access_token: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    encrypted_raw_response: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    connection: Mapped[IntegrationConnection] = relationship(
        "IntegrationConnection", back_populates="credential"
    )


class IntegrationEvent(Base):
    """Phase 6.1 — append-only activity log for a connection: every OAuth,
    sync, refresh, disconnect, and error event. Powers Sync History, the Error
    Center, Activity Logs, and Integration Analytics from ONE source of truth.

    Tenant-scoped (org + optional brand, mirroring the connection). `connection_id`
    is SET NULL on connection delete so history survives a hard-delete. Contains
    NO secrets — never the token, only metadata.
    """

    __tablename__ = "integration_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connection.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_slug: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # oauth_success | oauth_failure | sync_completed | sync_failed |
    # token_refreshed | disconnect | reconnect | error | webhook_received.
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # success | failure | info — drives Error Center filtering + analytics.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="info", index=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # rows_pulled, duration_ms, external_account, etc. Never a secret.
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
