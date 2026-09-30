"""Agent conversation persistence (Phase 2).

Two normalized, tenant-scoped tables: a conversation and its ordered messages.
Both inherit ``TenantMixin`` (organization_id + brand_id NOT NULL) so the
existing org-scoped RLS policies and service-layer brand filtering apply.

Stored content is plain conversational text + safe metadata only — never a
secret, credential, provider key, ORM/session object, callable reference, or a
chain-of-thought transcript. The canonical marketing context is NOT duplicated
into messages (it is rebuilt from MarketingBrainContext each turn).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class AgentConversation(Base, TenantMixin, TimestampMixin):
    """One conversational thread, scoped to a tenant brand."""

    __tablename__ = "agent_conversations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_agent_conversations_status"),
        Index("ix_agent_conversations_brand", "brand_id"),
        Index("ix_agent_conversations_brand_updated", "brand_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Who started it (best-effort reference; SET NULL on user delete).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")


class AgentMessage(Base, TenantMixin, TimestampMixin):
    """One message in a conversation. ``seq`` orders messages within a
    conversation (unique per conversation)."""

    __tablename__ = "agent_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'tool', 'system')", name="ck_agent_messages_role"
        ),
        UniqueConstraint("conversation_id", "seq", name="uq_agent_messages_conversation_seq"),
        Index("ix_agent_messages_conversation_seq", "conversation_id", "seq"),
        Index("ix_agent_messages_brand", "brand_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Safe display/audit metadata only (tools_consulted, evidence_status,
    # confidence, actions_blocked). NEVER secrets or chain-of-thought.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
