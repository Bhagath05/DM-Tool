"""CRM Email Platform ORM (Phase 6.5, Slice 4).

Templates (+ immutable version history + folders/categories), sequences (steps
with delays + stop/wait conditions), enrollments (lifecycle), and the email
record itself (tracking + provider metadata + CRM links). Every email links
(nullable, SET NULL) to lead / contact / company / deal / campaign and writes a
`crm_activities` row on send — reuse, no duplicate timeline.
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


class EmailFolder(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_email_folders"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_folders.id", ondelete="CASCADE"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EmailTemplate(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_email_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    # welcome|follow_up|proposal|reminder|thank_you|meeting|renewal|custom
    category: Mapped[str] = mapped_column(String(24), server_default="custom", index=True)
    subject: Mapped[str] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text)  # rich text / HTML
    variables: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", index=True)
    current_version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EmailTemplateVersion(Base, TenantMixin):
    """Immutable snapshot of a template at a point in time."""

    __tablename__ = "crm_email_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_templates.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    edit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailSequence(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_email_sequences"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="draft", index=True)  # draft|active|archived
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EmailSequenceStep(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_email_sequence_steps"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_sequences.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_templates.id", ondelete="SET NULL"), nullable=True
    )
    delay_hours: Mapped[int] = mapped_column(Integer, server_default="0")  # wait before this step
    wait_for_open: Mapped[bool] = mapped_column(Boolean, server_default="false")  # wait condition
    stop_on_reply: Mapped[bool] = mapped_column(Boolean, server_default="true")  # stop condition


class EmailEnrollment(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_email_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_email_sequences.id", ondelete="CASCADE"), index=True
    )
    to_email: Mapped[str] = mapped_column(String(320))
    # active|paused|completed|cancelled|stopped
    status: Mapped[str] = mapped_column(String(12), server_default="active", index=True)
    current_step: Mapped[int] = mapped_column(Integer, server_default="0")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True)
    enrolled_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Email(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_emails"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_email_templates.id", ondelete="SET NULL"), nullable=True)
    sequence_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_email_sequences.id", ondelete="SET NULL"), nullable=True)
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_email_enrollments.id", ondelete="SET NULL"), nullable=True)
    to_email: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text)
    # draft|queued|sent|delivered|bounced|failed
    status: Mapped[str] = mapped_column(String(12), server_default="draft", index=True)
    # Unguessable token embedded in the tracking pixel / links / unsubscribe URL.
    track_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, server_default="0")
    click_count: Mapped[int] = mapped_column(Integer, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CRM links (reuse existing rows) + the timeline activity created on send.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("crm_activities.id", ondelete="SET NULL"), nullable=True)
    sent_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
