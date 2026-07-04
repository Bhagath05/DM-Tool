"""CRM Email Platform schemas (Phase 6.5, Slice 4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EmailCategory = Literal[
    "welcome", "follow_up", "proposal", "reminder", "thank_you",
    "meeting", "renewal", "custom",
]
SequenceStatus = Literal["draft", "active", "archived"]
EnrollmentStatus = Literal["active", "paused", "completed", "cancelled", "stopped"]


# ---- folders ----
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None


class FolderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime


class FolderList(BaseModel):
    items: list[FolderResponse]


# ---- templates ----
class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: EmailCategory = "custom"
    subject: str = Field(min_length=1, max_length=400)
    body: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list, max_length=50)
    folder_id: uuid.UUID | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: EmailCategory | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=400)
    body: str | None = Field(default=None, min_length=1)
    variables: list[str] | None = Field(default=None, max_length=50)
    folder_id: uuid.UUID | None = None
    is_active: bool | None = None
    edit_summary: str | None = Field(default=None, max_length=280)


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    category: EmailCategory
    subject: str
    body: str
    variables: list
    folder_id: uuid.UUID | None
    is_active: bool
    current_version: int
    created_at: datetime
    updated_at: datetime


class TemplateList(BaseModel):
    items: list[TemplateResponse]
    total: int


class TemplateVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version_no: int
    subject: str
    body: str
    edit_summary: str | None
    created_by_user_id: str | None
    created_at: datetime


class TemplateVersionList(BaseModel):
    items: list[TemplateVersionResponse]


class RenderRequest(BaseModel):
    """Substitute variables to preview a template. Only the provided keys are
    filled; unknown {{placeholders}} are left intact (never fabricated)."""
    variables: dict[str, str] = Field(default_factory=dict)
    contact_id: uuid.UUID | None = None  # auto-fill from a real contact


class RenderedEmail(BaseModel):
    subject: str
    body: str
    unresolved: list[str]  # placeholders still unfilled


# ---- sequences ----
class StepInput(BaseModel):
    template_id: uuid.UUID | None = None
    delay_hours: int = Field(default=0, ge=0, le=8760)
    wait_for_open: bool = False
    stop_on_reply: bool = True


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    steps: list[StepInput] = Field(default_factory=list, max_length=50)


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: SequenceStatus | None = None


class StepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    position: int
    template_id: uuid.UUID | None
    delay_hours: int
    wait_for_open: bool
    stop_on_reply: bool


class SequenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    status: SequenceStatus
    created_at: datetime
    steps: list[StepResponse] = Field(default_factory=list)


class SequenceList(BaseModel):
    items: list[SequenceResponse]


# ---- enrollments ----
class EnrollRequest(BaseModel):
    contact_id: uuid.UUID | None = None
    to_email: str | None = Field(default=None, max_length=320)
    lead_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class BulkEnrollRequest(BaseModel):
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sequence_id: uuid.UUID
    to_email: str
    status: EnrollmentStatus
    current_step: int
    next_run_at: datetime | None
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    company_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    created_at: datetime


class EnrollmentList(BaseModel):
    items: list[EnrollmentResponse]
    total: int


# ---- emails ----
class SendEmailRequest(BaseModel):
    to_email: str = Field(max_length=320)
    subject: str = Field(min_length=1, max_length=400)
    body: str = Field(min_length=1)
    template_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class EmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    to_email: str
    subject: str
    status: str
    provider: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    clicked_at: datetime | None
    replied_at: datetime | None
    bounced_at: datetime | None
    unsubscribed_at: datetime | None
    open_count: int
    click_count: int
    contact_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    created_at: datetime


class EmailList(BaseModel):
    items: list[EmailResponse]
    total: int


class EmailStats(BaseModel):
    """Tracking dashboard aggregates (real counts only)."""
    sent: int
    delivered: int
    opened: int
    clicked: int
    replied: int
    bounced: int
    unsubscribed: int
    open_rate: float
    click_rate: float
    reply_rate: float
    bounce_rate: float


# ---- provider webhook ----
class ProviderEvent(BaseModel):
    """Normalised inbound provider event (delivered / bounced / replied)."""
    event: Literal["delivered", "bounced", "replied", "complained"]
    message_id: str | None = None
    track_token: str | None = None
    detail: str | None = None
