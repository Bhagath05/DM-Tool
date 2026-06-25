"""Growth module Pydantic I/O."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ObjectiveKindOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    category: str
    kpi_hint: str | None = None
    default_channels: list[str] = Field(default_factory=list)


class CreateObjectiveRequest(BaseModel):
    objective_kind: str = Field(min_length=1, max_length=48)
    statement: str = Field(min_length=1, max_length=2000)  # the free-text goal
    audience_hypothesis: str | None = Field(default=None, max_length=2000)
    budget_cents: int | None = Field(default=None, ge=0)


class ObjectiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    objective_kind: str
    statement: str
    audience_hypothesis: str | None = None
    budget_cents: int | None = None
    status: str
    created_at: datetime


class ObjectiveList(BaseModel):
    items: list[ObjectiveResponse]


class BuiltAssetOut(BaseModel):
    """One creative produced for a campaign — links to its editable design."""

    design_id: uuid.UUID
    name: str
    creative_type: str
    media_type: str
    aspect: str
    current_revision: int
    rationale: str | None = None


class CampaignStrategyOut(BaseModel):
    objective_summary: str
    audience: str
    hook: str
    value_prop: str
    proof_point: str | None = None
    cta_angle: str
    channels: list[str] = Field(default_factory=list)


class CampaignBuildResponse(BaseModel):
    """Result of building a campaign from an objective: the strategy (the why)
    + the editable assets (the what)."""

    objective_id: uuid.UUID
    strategy: CampaignStrategyOut
    assets: list[BuiltAssetOut]
