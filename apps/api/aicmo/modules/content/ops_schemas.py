"""Phase 6.2B — enterprise content-ops schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.content.ops_service import REVIEW_STATUSES  # noqa: F401


# ---- versions ----
class ContentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_no: int
    edit_source: str
    change_summary: str | None
    author_user_id: str
    created_at: datetime


class ContentVersionList(BaseModel):
    items: list[ContentVersionResponse]


class VersionOutput(BaseModel):
    version_no: int
    edit_source: str
    output: dict[str, Any]


class VersionCompare(BaseModel):
    a: VersionOutput
    b: VersionOutput


class RestoreRequest(BaseModel):
    version_no: int = Field(ge=1)


class EditRequest(BaseModel):
    output: dict[str, Any]
    change_summary: str | None = Field(default=None, max_length=280)


# ---- review ----
class ReviewTransitionRequest(BaseModel):
    to_status: Literal[
        "draft", "in_review", "changes_requested", "approved", "rejected",
        "published", "archived",
    ]
    reason: str | None = Field(default=None, max_length=1000)


class ReviewEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: str
    to_status: str
    reason: str | None
    reviewer_user_id: str
    created_at: datetime


class ReviewHistoryList(BaseModel):
    items: list[ReviewEventResponse]


# ---- folders ----
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["folder", "collection"] = "folder"
    parent_id: uuid.UUID | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


class FolderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    parent_id: uuid.UUID | None
    pinned: bool
    created_at: datetime


class FolderList(BaseModel):
    items: list[FolderResponse]


class AssignFolderRequest(BaseModel):
    content_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    folder_id: uuid.UUID | None = None


# ---- comments ----
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: uuid.UUID | None = None
    mentions: list[str] = Field(default_factory=list, max_length=20)


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_id: uuid.UUID
    parent_id: uuid.UUID | None
    author_user_id: str
    body: str
    mentions: list[str]
    resolved: bool
    resolved_by_user_id: str | None
    created_at: datetime


class CommentList(BaseModel):
    items: list[CommentResponse]


class CommentResolveRequest(BaseModel):
    resolved: bool
