from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ModelView(BaseModel):
    model_id: str
    provider: str
    task: str
    display_name: str
    output_kind: str
    available: bool
    verified: bool
    aspect_ratios: list[str]
    resolutions: list[str]
    cost_cents: int | None
    cost_unit: str | None
    unavailable_reason: str | None


class GenerateRequest(BaseModel):
    mode: Literal["auto", "manual", "compare"]
    task: Literal["image.generate"] = "image.generate"
    prompt: str = Field(min_length=1, max_length=4000)
    model_ids: list[str] | None = None
    aspect_ratio: str | None = "1:1"
    resolution: str | None = "standard"


class ModelResult(BaseModel):
    model_id: str
    provider: str
    status: str
    error: str | None = None
    duration_ms: int | None = None
    cost_cents: int | None = None
    cost_unit: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    storage_backend: str | None = None
    storage_key: str | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    mode: str
    task: str
    status: str
    explanation: str | None
    results: list[ModelResult]
    error_message: str | None
