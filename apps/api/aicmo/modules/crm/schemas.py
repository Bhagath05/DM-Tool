"""CRM schemas (Phase 6.5)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PipelineKind = Literal["marketing", "sales", "enterprise", "agency", "custom"]
DealStatus = Literal["open", "won", "lost"]
Priority = Literal["low", "medium", "high"]


# ---- pipelines ----
class StageInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    probability: int = Field(default=0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: PipelineKind = "sales"
    stages: list[StageInput] = Field(default_factory=list, max_length=30)


class PipelineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool


class PipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    is_default: bool
    archived: bool
    created_at: datetime
    stages: list[StageResponse] = Field(default_factory=list)


class PipelineList(BaseModel):
    items: list[PipelineResponse]


class ReorderStagesRequest(BaseModel):
    stage_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)


# ---- deals ----
class DealProduct(BaseModel):
    name: str
    quantity: int = 1
    price: float = 0.0


class DealCreate(BaseModel):
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=64)
    value: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    probability: int | None = Field(default=None, ge=0, le=100)
    priority: Priority = "medium"
    expected_close_date: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=30)
    products: list[DealProduct] = Field(default_factory=list, max_length=50)
    competitors: list[str] = Field(default_factory=list, max_length=20)


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=64)
    value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    probability: int | None = Field(default=None, ge=0, le=100)
    priority: Priority | None = None
    expected_close_date: date | None = None
    owner_user_id: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = Field(default=None, max_length=30)
    products: list[DealProduct] | None = Field(default=None, max_length=50)
    competitors: list[str] | None = Field(default=None, max_length=20)


class DealMoveRequest(BaseModel):
    stage_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)


class DealCloseRequest(BaseModel):
    status: Literal["won", "lost"]
    lost_reason: str | None = Field(default=None, max_length=500)


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    title: str
    company: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    value: float
    currency: str
    probability: int | None
    status: DealStatus
    priority: Priority
    expected_close_date: date | None
    owner_user_id: str | None
    source: str | None
    tags: list[Any]
    products: list[Any]
    competitors: list[Any]
    lost_reason: str | None
    won_at: datetime | None
    lost_at: datetime | None
    ai_next_action: dict[str, Any] | None
    ai_generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DealList(BaseModel):
    items: list[DealResponse]
    total: int


class DealEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID | None
    from_status: str | None
    to_status: str | None
    actor_user_id: str | None
    note: str | None
    created_at: datetime


class DealEventList(BaseModel):
    items: list[DealEventResponse]


# ---- AI next action (grounded; carries the recommendation contract) ----
class DealNextAction(BaseModel):
    recommendation: str = Field(description="The single next action for this deal.")
    reason: str = Field(max_length=200, description="What real deal/lead data this drew on.")
    confidence: int = Field(ge=0, le=100)
    expected_result: str = Field(description="Ranged outcome if the action is taken.")
    risk_score: int = Field(ge=0, le=100, description="Probability-of-loss signal.")
    opportunity_score: int = Field(ge=0, le=100, description="Upside/priority signal.")


# ---- analytics (executive dashboard, Part 9) ----
class StageBreakdown(BaseModel):
    stage_id: uuid.UUID | None
    stage_name: str
    count: int
    value: float


class PipelineAnalytics(BaseModel):
    pipeline_id: uuid.UUID | None
    open_deals: int
    won_deals: int
    lost_deals: int
    pipeline_value: float          # Σ open value
    weighted_forecast: float       # Σ open value × probability
    won_value: float
    win_rate: float                # won / (won + lost)
    avg_deal_size: float           # avg won value
    conversion_rate: float         # won / total
    by_stage: list[StageBreakdown]
