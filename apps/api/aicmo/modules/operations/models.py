"""Phase 4 — Operations Engine ORM models.

`MetricSnapshot` — a periodic, tenant-scoped point-in-time capture of a brand's
REAL metrics (reused from existing services, never re-derived). The time series
these form is what Event Detection (4.2) compares to spot changes.

`OperationsRun` — one row per continuous-loop cycle (system-wide, not tenant
scoped). Doubles as the audit trail for ticks, the idempotency/throttle anchor,
and the "system health / last run" data for the Ops dashboard (4.7).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class MetricSnapshot(Base, TimestampMixin, TenantMixin):
    """A brand's real metrics at a moment in time. Cheap (no LLM); the source of
    truth for trend/event detection."""

    __tablename__ = "metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # When the snapshot was taken (== created_at at insert; explicit for the
    # time-series read path).
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # Flat metric map — {total_leads, leads_7d, conversion_rate, published_posts,
    # performance_rows, ...}. Free-shape JSONB so new metrics don't need a
    # migration; every value comes from a real existing service read.
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Which source reads succeeded (transparency; a degraded source doesn't sink
    # the snapshot).
    sources_ok: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


class OperationsRun(Base, TimestampMixin):
    """One continuous-loop cycle. System-wide (spans all tenants), so NOT a
    TenantMixin row — it's the operator-facing audit + idempotency anchor."""

    __tablename__ = "operations_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "api" (tick endpoint) | "cron" (future Arq worker) | "manual".
    trigger: Mapped[str] = mapped_column(
        String(16), default="api", server_default="api"
    )
    # "completed" | "throttled" | "partial" | "failed".
    status: Mapped[str] = mapped_column(
        String(16), default="completed", server_default="completed"
    )
    brands_scanned: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    snapshots_captured: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    events_detected: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    # Per-brand summary + any errors (operator visibility).
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
