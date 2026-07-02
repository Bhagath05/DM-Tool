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

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
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


class DetectedEvent(Base, TimestampMixin, TenantMixin):
    """Phase 4.2 — a meaningful change detected by comparing consecutive metric
    snapshots. Deterministic (no LLM); every field is grounded in a real metric
    delta. Becomes structured input for the Decision Engine (4.6). One active
    event per (brand, type) via `dedupe_key` so a persistent condition isn't
    re-emitted every cycle."""

    __tablename__ = "detected_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # e.g. no_recent_leads | leads_declining | leads_surge | traffic_spike |
    # traffic_drop | conversion_drop | publishing_failures | performance_flagged.
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(
        String(16), default="medium", server_default="medium"
    )
    direction: Mapped[str] = mapped_column(
        String(16), default="negative", server_default="negative"
    )
    metric: Mapped[str] = mapped_column(String(48))
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # Stable key to avoid re-emitting the same active condition each cycle.
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True)

    # new → acknowledged → actioned → dismissed | resolved.
    status: Mapped[str] = mapped_column(
        String(16), default="new", server_default="new", index=True
    )


class OperationalGoal(Base, TimestampMixin, TenantMixin):
    """Phase 4.3 — a user-defined marketing goal the AI continuously works toward.
    Progress is measured from real metric snapshots (deterministic; never
    invented). Active goals feed Strategy, Planner, and the Decision Engine."""

    __tablename__ = "operational_goals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)  # creator

    title: Mapped[str] = mapped_column(Text)
    # leads | website_traffic | conversions | content_output | roas | cpa |
    # instagram_followers | linkedin_followers | appointments.
    metric: Mapped[str] = mapped_column(String(32), index=True)
    # increase | decrease | reach.
    goal_type: Mapped[str] = mapped_column(
        String(16), default="increase", server_default="increase"
    )
    target_value: Mapped[float] = mapped_column(Float)
    # Captured at creation from the latest snapshot (0 if none / unmeasured).
    baseline_value: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0"
    )
    current_value: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0"
    )
    timeframe_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # False when the goal's metric isn't captured yet (roas/cpa/followers/
    # appointments) — the goal is tracked but progress is honestly "unmeasured".
    measurable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # active → achieved | paused | archived.
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", index=True
    )
    achieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_measured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ScheduledWork(Base, TimestampMixin, TenantMixin):
    """Phase 4.4 — a unit of marketing work the AI has SCHEDULED (not executed).
    Proposed deterministically from open events + goals, each gated by the
    Autonomy Policy. Nothing runs from here unless policy + the master switch
    permit; by default every item awaits human approval."""

    __tablename__ = "scheduled_work"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # What kind of work: content_generation | campaign_update | budget_change |
    # blog | reel | ad | email | weekly_report.
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # The Autonomy-Policy action type this maps to (governs approval).
    action_type: Mapped[str] = mapped_column(String(32))

    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)  # WHY — grounded in the source

    # event | goal | recurring | decision.
    source_kind: Mapped[str] = mapped_column(String(16), default="event")
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    priority: Mapped[str] = mapped_column(
        String(16), default="medium", server_default="medium"
    )

    # Policy evaluation snapshot (from autonomy.evaluate_policy at scheduling).
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    auto_eligible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    policy_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # proposed → awaiting_approval → approved → queued → executed | dismissed |
    # failed. Default awaiting_approval: safe until a human (or policy) releases it.
    status: Mapped[str] = mapped_column(
        String(20),
        default="awaiting_approval",
        server_default="awaiting_approval",
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Dedupe: one open item per (brand, kind, source).
    dedupe_key: Mapped[str] = mapped_column(String(160), index=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class OperationsNotification(Base, TimestampMixin, TenantMixin):
    """Phase 4.8 — an in-app notification the operations loop raises for the
    owner. Reuses the existing notifications catalog's CATEGORY taxonomy (so the
    future email/slack/sms dispatcher can gate delivery via the preference
    matrix); the in-app feed itself works today. Deduped so a standing condition
    notifies once."""

    __tablename__ = "operations_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # One of the notifications-catalog categories (campaign_alert / winner_alert
    # / weekly_digest / system_alert / ...). Validated against the catalog.
    category: Mapped[str] = mapped_column(String(32), index=True)
    # event | approval | goal | learning | budget | competitor | system.
    kind: Mapped[str] = mapped_column(String(24), index=True)
    severity: Mapped[str] = mapped_column(
        String(16), default="info", server_default="info"
    )
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(180), index=True)
    read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
