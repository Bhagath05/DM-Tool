"""Phase 4 — Operations Engine schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GoalMetric = Literal[
    "leads",
    "website_traffic",
    "conversions",
    "content_output",
    "roas",
    "cpa",
    "instagram_followers",
    "linkedin_followers",
    "appointments",
]
GoalType = Literal["increase", "decrease", "reach"]


class MetricSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    captured_at: datetime
    metrics: dict
    sources_ok: list[str]


class BrandCycleResult(BaseModel):
    """What happened for one brand in a cycle."""

    brand_id: str
    snapshot_captured: bool
    reason: str
    metrics_count: int = 0
    events_detected: int = 0
    work_scheduled: int = 0


class TickResult(BaseModel):
    """The outcome of one continuous-loop cycle (the /operations/tick response)."""

    run_id: str | None = None
    trigger: str
    status: str = Field(description="completed | throttled | partial | failed")
    brands_scanned: int = 0
    snapshots_captured: int = 0
    events_detected: int = 0
    work_scheduled: int = 0
    duration_ms: int = 0
    detail: list[BrandCycleResult] = Field(default_factory=list)
    note: str | None = None


class OperationsRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    started_at: datetime
    finished_at: datetime | None
    trigger: str
    status: str
    brands_scanned: int
    snapshots_captured: int
    events_detected: int


class MonitoringView(BaseModel):
    """Tenant-scoped monitoring read for the Ops dashboard (4.7)."""

    latest: MetricSnapshotResponse | None
    history: list[MetricSnapshotResponse]
    monitored: bool = Field(description="True once at least one snapshot exists.")
    note: str | None = None


class DetectedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    detected_at: datetime
    event_type: str
    severity: str
    direction: str
    metric: str
    previous_value: float | None
    current_value: float | None
    change_pct: float | None
    title: str
    summary: str
    evidence: list[str]
    status: str


class EventsView(BaseModel):
    items: list[DetectedEventResponse]
    open_count: int = Field(description="Events still needing attention (new/acknowledged).")
    note: str | None = None


class GoalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    metric: GoalMetric
    goal_type: GoalType = "increase"
    target_value: float = Field(gt=0)
    timeframe_days: int | None = Field(default=None, ge=1, le=365)


class GoalStatusUpdate(BaseModel):
    status: Literal["active", "paused", "archived"]


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    title: str
    metric: str
    goal_type: str
    target_value: float
    baseline_value: float
    current_value: float
    timeframe_days: int | None
    measurable: bool
    status: str
    achieved_at: datetime | None
    last_measured_at: datetime | None
    progress_pct: int | None = Field(
        default=None, description="0-100 progress; null when not yet measurable."
    )


class GoalList(BaseModel):
    items: list[GoalResponse]


class WorkItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    kind: str
    action_type: str
    title: str
    description: str
    rationale: str
    source_kind: str
    priority: str
    requires_approval: bool
    auto_eligible: bool
    policy_mode: str | None
    status: str
    scheduled_for: datetime | None
    created_at: datetime


class WorkList(BaseModel):
    items: list[WorkItemResponse]
    awaiting_approval: int = Field(description="Items still needing human approval.")


class WorkStatusUpdate(BaseModel):
    # Human decisions on a scheduled item. 'approved' releases it; 'dismissed'
    # cancels it. Execution wiring stays gated (4.9), so approving does not
    # itself run anything yet.
    status: Literal["approved", "dismissed"]
