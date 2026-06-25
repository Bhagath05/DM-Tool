"""Creative Studio design — HTTP I/O schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateDesignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    media_type: Literal["image", "carousel", "composite", "video"] = "image"
    format_slug: str | None = Field(default=None, max_length=48)
    growth_objective_id: uuid.UUID | None = None
    creative_project_id: uuid.UUID | None = None
    # Optional seed copy for the CS1 stub composer (CS3 replaces with real AI).
    headline: str | None = Field(default=None, max_length=200)
    subhead: str | None = Field(default=None, max_length=300)
    cta: str | None = Field(default=None, max_length=80)


class DesignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    media_type: str
    format_slug: str | None = None
    growth_objective_id: uuid.UUID | None = None
    current_revision: int
    head_revision_id: uuid.UUID | None = None
    default_mode: str
    status: str
    doc: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DesignSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    media_type: str
    format_slug: str | None = None
    current_revision: int
    default_mode: str
    status: str
    updated_at: datetime


class DesignList(BaseModel):
    items: list[DesignSummary]


class AiEditRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=1000)
    base_revision: int = Field(ge=0)


class NlEditRequest(BaseModel):
    """One instruction; the router decides edit/regenerate/transform/restyle/
    variant. `preview=True` (default) plans without committing a revision."""

    instruction: str = Field(min_length=1, max_length=1000)
    base_revision: int = Field(ge=0)
    preview: bool = True


class NlEditResponse(BaseModel):
    op_class: str
    confidence: int
    summary: str
    committed: bool
    design_id: uuid.UUID          # the source/affected design
    current_revision: int
    proposed_doc: dict[str, Any] | None = None      # preview of in-place edits
    created_design_ids: list[uuid.UUID] = Field(default_factory=list)  # restyle/transform/variant
    notes: str | None = None


class ProEditRequest(BaseModel):
    base_revision: int = Field(ge=0)
    ops: list[dict[str, Any]] | None = None
    doc: dict[str, Any] | None = None


class TransformRequest(BaseModel):
    kind: Literal["reformat", "recompose", "remediate"]
    base_revision: int = Field(ge=0)
    target_format_slug: str | None = Field(default=None, max_length=48)


class RestyleRequest(BaseModel):
    style: str = Field(min_length=1, max_length=80)
    base_revision: int = Field(ge=0)


class RevertRequest(BaseModel):
    target_revision: int = Field(ge=1)
    base_revision: int = Field(ge=0)


class RevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_n: int
    parent_revision_id: uuid.UUID | None = None
    source: str
    actor_kind: str
    mode: str
    review_status: str
    created_by_user_id: str | None = None
    edit_summary: str | None = None
    created_at: datetime


class RevisionList(BaseModel):
    items: list[RevisionSummary]


class BrandAssetCreate(BaseModel):
    kind: Literal["logo", "font", "image", "color", "icon"]
    label: str | None = Field(default=None, max_length=128)
    storage_backend: str | None = Field(default=None, max_length=16)
    storage_key: str | None = Field(default=None, max_length=512)
    mime_type: str | None = Field(default=None, max_length=48)
    meta: dict[str, Any] = Field(default_factory=dict)


class BrandAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    label: str | None = None
    storage_backend: str | None = None
    storage_key: str | None = None
    mime_type: str | None = None
    is_favorite: bool = False
    url: str | None = None  # short-lived signed URL (computed in the router)
    created_at: datetime


class BrandAssetList(BaseModel):
    items: list[BrandAssetResponse]


# ---- CS6: video rendering + publishing ----
class VideoRenderResponse(BaseModel):
    """Result of kicking off a render — the work runs async on an Arq worker."""

    design_id: uuid.UUID
    project_id: uuid.UUID
    status: str  # draft|scripting|rendering|post_processing|ready|failed_rendering


class VideoStatusResponse(BaseModel):
    design_id: uuid.UUID
    project_id: uuid.UUID | None = None
    status: str
    asset_id: uuid.UUID | None = None
    video_url: str | None = None
    captions_url: str | None = None
    duration_ms: int | None = None
    scenes: int | None = None


class ExportRequest(BaseModel):
    platforms: list[
        Literal["instagram_reels", "tiktok", "youtube_shorts", "facebook_reels", "linkedin"]
    ] = Field(min_length=1)


class ExportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_platform: str | None = None
    format_slug: str | None = None
    width: int | None = None
    height: int | None = None
    status: str


class ExportList(BaseModel):
    items: list[ExportItem]
