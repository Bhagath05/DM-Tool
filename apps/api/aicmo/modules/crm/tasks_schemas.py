"""CRM Tasks & Calendar schemas (Phase 6.5, Slice 3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityType = Literal[
    "call", "meeting", "demo", "follow_up", "email_reminder",
    "internal", "approval", "custom",
]
TaskStatus = Literal["open", "in_progress", "completed", "cancelled"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
RecurrenceFreq = Literal["daily", "weekly", "monthly"]


class Recurrence(BaseModel):
    freq: RecurrenceFreq
    interval: int = Field(default=1, ge=1, le=365)
    until: datetime | None = None
    count: int | None = Field(default=None, ge=1, le=365)


class TaskLinks(BaseModel):
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class TaskCreate(TaskLinks):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    activity_type: ActivityType = "follow_up"
    priority: TaskPriority = "medium"
    owner_user_id: str | None = Field(default=None, max_length=255)
    assignee_user_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    recurrence: Recurrence | None = None
    calendar_event: bool = False
    estimated_minutes: int | None = Field(default=None, ge=0, le=100000)
    notes: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=30)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    activity_type: ActivityType | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    owner_user_id: str | None = Field(default=None, max_length=255)
    assignee_user_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    calendar_event: bool | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=100000)
    actual_minutes: int | None = Field(default=None, ge=0, le=100000)
    notes: str | None = None
    attachments: list[dict[str, Any]] | None = Field(default=None, max_length=50)
    tags: list[str] | None = Field(default=None, max_length=30)
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class TaskCompleteRequest(BaseModel):
    actual_minutes: int | None = Field(default=None, ge=0, le=100000)
    notes: str | None = Field(default=None, max_length=2000)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    activity_type: ActivityType
    status: TaskStatus
    priority: TaskPriority
    owner_user_id: str | None
    assignee_user_id: str | None
    due_at: datetime | None
    reminder_at: datetime | None
    is_recurring: bool
    recurrence: dict[str, Any] | None
    recurrence_parent_id: uuid.UUID | None
    calendar_event: bool
    estimated_minutes: int | None
    actual_minutes: int | None
    completed_at: datetime | None
    notes: str | None
    attachments: list[Any]
    tags: list[Any]
    lead_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    company_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    source: str | None
    ai_suggestion: dict[str, Any] | None
    ai_generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    items: list[TaskResponse]
    total: int


# ---- AI (grounded task assistant) ----
class TaskSuggestion(BaseModel):
    recommended_priority: TaskPriority
    recommended_due_in_days: int = Field(ge=0, le=90)
    follow_up: str = Field(description="The single best next task for this record.")
    risk_alert: str = Field(description="One risk to watch, grounded in the data (or 'None').")
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200, description="What real CRM data this drew on.")
