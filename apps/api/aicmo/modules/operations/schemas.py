"""Phase 4 — Operations Engine schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class TickResult(BaseModel):
    """The outcome of one continuous-loop cycle (the /operations/tick response)."""

    run_id: str | None = None
    trigger: str
    status: str = Field(description="completed | throttled | partial | failed")
    brands_scanned: int = 0
    snapshots_captured: int = 0
    events_detected: int = 0
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
