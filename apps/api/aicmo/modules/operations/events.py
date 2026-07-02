"""Phase 4.2 — Event Detection Engine.

Deterministic (NO LLM): compares the two most recent metric snapshots for a
brand and emits structured `DetectedEvent`s grounded entirely in real deltas.
These become the structured input the Decision Engine (4.6) reasons over.

Idempotent: one active event per (brand, event_type) via `dedupe_key`, so a
persistent condition (e.g. "no leads") isn't re-created every cycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.operations.models import DetectedEvent

log = structlog.get_logger()

# Relative-change thresholds (fractions). Tuned to avoid noise on tiny numbers.
_LEADS_DROP = -0.40
_LEADS_SURGE = 0.50
_TRAFFIC_SPIKE = 0.50
_TRAFFIC_DROP = -0.40
_CONV_DROP = -0.30


@dataclass
class EventDraft:
    event_type: str
    severity: str
    direction: str
    metric: str
    title: str
    summary: str
    previous_value: float | None = None
    current_value: float | None = None
    change_pct: float | None = None
    evidence: list[str] = field(default_factory=list)


def _pct(prev: float, curr: float) -> float | None:
    return (curr - prev) / prev if prev else None


def _g(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def detect(current: dict, previous: dict) -> list[EventDraft]:
    """Pure detection over two metric maps (newest, prior). Returns 0+ drafts."""
    out: list[EventDraft] = []

    # --- Leads ------------------------------------------------------------
    p_leads, c_leads = _g(previous, "leads_7d"), _g(current, "leads_7d")
    if p_leads >= 3 and c_leads == 0:
        out.append(EventDraft(
            "no_recent_leads", "high", "negative", "leads_7d",
            "Leads have stopped",
            f"You had {int(p_leads)} leads in the prior window and 0 now — the lead flow dried up.",
            p_leads, c_leads, -1.0,
            [f"leads_7d: {int(p_leads)} → 0"],
        ))
    else:
        ch = _pct(p_leads, c_leads)
        if ch is not None and ch <= _LEADS_DROP:
            out.append(EventDraft(
                "leads_declining", "high" if ch <= -0.6 else "medium", "negative",
                "leads_7d", "Leads are dropping",
                f"Leads in the last 7 days fell {abs(ch) * 100:.0f}% ({int(p_leads)} → {int(c_leads)}).",
                p_leads, c_leads, round(ch, 4),
                [f"leads_7d: {int(p_leads)} → {int(c_leads)}"],
            ))
        elif ch is not None and ch >= _LEADS_SURGE and (c_leads - p_leads) >= 3:
            out.append(EventDraft(
                "leads_surge", "medium", "positive", "leads_7d",
                "Leads are surging",
                f"Leads jumped {ch * 100:.0f}% ({int(p_leads)} → {int(c_leads)}) — worth doubling down.",
                p_leads, c_leads, round(ch, 4),
                [f"leads_7d: {int(p_leads)} → {int(c_leads)}"],
            ))

    # --- Traffic ----------------------------------------------------------
    p_views, c_views = _g(previous, "total_views"), _g(current, "total_views")
    ch = _pct(p_views, c_views)
    if ch is not None and ch >= _TRAFFIC_SPIKE and (c_views - p_views) >= 20:
        out.append(EventDraft(
            "traffic_spike", "medium", "positive", "total_views",
            "Website traffic spiked",
            f"Visits rose {ch * 100:.0f}% ({int(p_views)} → {int(c_views)}) — capitalise while attention is high.",
            p_views, c_views, round(ch, 4),
            [f"total_views: {int(p_views)} → {int(c_views)}"],
        ))
    elif ch is not None and ch <= _TRAFFIC_DROP and p_views >= 20:
        out.append(EventDraft(
            "traffic_drop", "high" if ch <= -0.6 else "medium", "negative",
            "total_views", "Website traffic dropped",
            f"Visits fell {abs(ch) * 100:.0f}% ({int(p_views)} → {int(c_views)}).",
            p_views, c_views, round(ch, 4),
            [f"total_views: {int(p_views)} → {int(c_views)}"],
        ))

    # --- Conversion -------------------------------------------------------
    p_conv, c_conv = _g(previous, "conversion_rate"), _g(current, "conversion_rate")
    ch = _pct(p_conv, c_conv)
    if ch is not None and ch <= _CONV_DROP and p_conv > 0:
        out.append(EventDraft(
            "conversion_drop", "high", "negative", "conversion_rate",
            "Conversion rate is falling",
            f"Visitor-to-lead conversion dropped {abs(ch) * 100:.0f}% ({p_conv * 100:.1f}% → {c_conv * 100:.1f}%).",
            round(p_conv, 6), round(c_conv, 6), round(ch, 4),
            [f"conversion_rate: {p_conv * 100:.1f}% → {c_conv * 100:.1f}%"],
        ))

    # --- Publishing failures ---------------------------------------------
    p_fail, c_fail = _g(previous, "failed_posts"), _g(current, "failed_posts")
    if c_fail > p_fail:
        out.append(EventDraft(
            "publishing_failures", "high", "negative", "failed_posts",
            "Posts failed to publish",
            f"{int(c_fail - p_fail)} new publishing failure(s) — some content didn't go out.",
            p_fail, c_fail, None,
            [f"failed_posts: {int(p_fail)} → {int(c_fail)}"],
        ))

    # --- Performance diagnostics -----------------------------------------
    p_diag, c_diag = _g(previous, "performance_diagnostics"), _g(current, "performance_diagnostics")
    if c_diag > p_diag:
        out.append(EventDraft(
            "performance_flagged", "medium", "negative", "performance_diagnostics",
            "New performance issues flagged",
            f"{int(c_diag - p_diag)} new performance diagnostic(s) need attention.",
            p_diag, c_diag, None,
            [f"performance_diagnostics: {int(p_diag)} → {int(c_diag)}"],
        ))

    return out


async def _active_types(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> set[str]:
    """event_types that already have an unresolved event for this brand."""
    stmt = select(DetectedEvent.event_type).where(
        DetectedEvent.brand_id == brand_id,
        DetectedEvent.status.in_(("new", "acknowledged")),
    )
    return {row[0] for row in (await session.execute(stmt)).all()}


async def detect_and_store(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    current: dict,
    previous: dict,
    now: datetime | None = None,
) -> list[DetectedEvent]:
    """Detect events from two snapshots and persist the NEW ones (deduped
    against still-active events of the same type). Does not commit."""
    now = now or datetime.now(UTC)
    drafts = detect(current, previous)
    if not drafts:
        return []

    active = await _active_types(session, brand_id=brand_id)
    created: list[DetectedEvent] = []
    for d in drafts:
        if d.event_type in active:
            continue  # already open — don't re-emit
        row = DetectedEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_id=brand_id,
            detected_at=now,
            event_type=d.event_type,
            severity=d.severity,
            direction=d.direction,
            metric=d.metric,
            previous_value=d.previous_value,
            current_value=d.current_value,
            change_pct=d.change_pct,
            title=d.title,
            summary=d.summary,
            evidence=list(d.evidence),
            dedupe_key=f"{brand_id}:{d.event_type}",
            status="new",
        )
        session.add(row)
        created.append(row)
    return created
