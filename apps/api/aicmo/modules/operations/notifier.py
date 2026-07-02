"""Phase 4.8 — Notification Center.

Raises in-app notifications from the operations loop, categorised with the
EXISTING notifications catalog taxonomy (so the future dispatcher can gate
email/slack/sms via the preference matrix). Deduped so a standing condition
notifies once. Grounded in real rows only — never invented.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.notifications.catalog import all_category_ids
from aicmo.modules.operations.models import OperationalGoal, OperationsNotification

log = structlog.get_logger()


async def _existing_keys(session: AsyncSession, *, brand_id: uuid.UUID) -> set[str]:
    stmt = select(OperationsNotification.dedupe_key).where(
        OperationsNotification.brand_id == brand_id,
    )
    return {row[0] for row in (await session.execute(stmt)).all()}


def _emit(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    category: str,
    kind: str,
    title: str,
    body: str,
    dedupe_key: str,
    now: datetime,
    severity: str = "info",
    link: str | None = None,
    source_id: uuid.UUID | None = None,
    existing: set[str] | None = None,
) -> bool:
    """Stage one notification if not already present. Validates category against
    the shared catalog (falls back to system_alert). Returns True if staged."""
    if existing is not None and dedupe_key in existing:
        return False
    if category not in all_category_ids():
        category = "system_alert"
    session.add(OperationsNotification(
        id=uuid.uuid4(),
        organization_id=organization_id,
        brand_id=brand_id,
        category=category,
        kind=kind,
        severity=severity,
        title=title,
        body=body,
        link=link,
        source_id=source_id,
        dedupe_key=dedupe_key,
        read=False,
    ))
    if existing is not None:
        existing.add(dedupe_key)
    return True


async def emit_for_cycle(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    new_events: list,
    work_created: int,
    now: datetime | None = None,
) -> int:
    """Raise notifications for this cycle's real changes: high-severity events,
    new approvals awaiting the owner, and goals just achieved. Deduped. Returns
    the number staged. Does not commit."""
    now = now or datetime.now(UTC)
    existing = await _existing_keys(session, brand_id=brand_id)
    staged = 0

    # Important events / performance drops → campaign health alert.
    for ev in new_events:
        if getattr(ev, "severity", "") not in ("critical", "high"):
            continue
        if _emit(
            session, organization_id=organization_id, brand_id=brand_id,
            category="campaign_alert", kind="event",
            title=ev.title, body=ev.summary, severity=ev.severity,
            link="/operations", source_id=ev.id,
            dedupe_key=f"event:{ev.id}", now=now, existing=existing,
        ):
            staged += 1

    # Required approvals — bucketed per hour so it doesn't spam.
    if work_created:
        if _emit(
            session, organization_id=organization_id, brand_id=brand_id,
            category="campaign_alert", kind="approval",
            title="Work needs your approval",
            body=f"{work_created} new item(s) the AI scheduled are awaiting your approval.",
            severity="medium", link="/operations",
            dedupe_key=f"approval:{brand_id}:{now:%Y-%m-%d-%H}", now=now, existing=existing,
        ):
            staged += 1

    # Goal achievements → winning alert.
    achieved = list((await session.execute(
        select(OperationalGoal).where(
            OperationalGoal.brand_id == brand_id,
            OperationalGoal.status == "achieved",
            OperationalGoal.achieved_at.is_not(None),
            OperationalGoal.achieved_at >= now,
        )
    )).scalars().all())
    for g in achieved:
        if _emit(
            session, organization_id=organization_id, brand_id=brand_id,
            category="winner_alert", kind="goal",
            title="Goal achieved 🎉", body=f"You hit your goal: {g.title}.",
            severity="info", link="/operations", source_id=g.id,
            dedupe_key=f"goal:{g.id}", now=now, existing=existing,
        ):
            staged += 1

    return staged
