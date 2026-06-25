"""Creative cost ledger — what WE pay providers (Creative Core V0).

Distinct from billing `usage_event` (the customer's metered quota). This
records provider + storage cost + render duration per stage, rolled up to
the project and the org. Drives gross-margin reporting + the per-org
budget cap. Best-effort: a ledger failure never blocks generation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.creative.models import CreativeCostEvent, CreativeProject

log = structlog.get_logger()


async def record_cost(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    stage: str,
    provider: str,
    cost_cents: int,
    creative_project_id: uuid.UUID | None = None,
    media_type: str | None = None,
    units: float = 0,
    unit_cost_cents: float = 0,
    duration_ms: int | None = None,
) -> None:
    """Append one ledger row. Never raises."""
    try:
        session.add(
            CreativeCostEvent(
                organization_id=organization_id,
                brand_id=brand_id,
                creative_project_id=creative_project_id,
                media_type=media_type,
                stage=stage,
                provider=provider,
                units=units,
                unit_cost_cents=unit_cost_cents,
                cost_cents=cost_cents,
                duration_ms=duration_ms,
            )
        )
        await session.flush()
    except Exception as e:  # noqa: BLE001
        log.warning("creative.cost_record_failed", stage=stage, error=str(e))


async def project_cost_cents(session: AsyncSession, *, creative_project_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.sum(CreativeCostEvent.cost_cents), 0)).where(
        CreativeCostEvent.creative_project_id == creative_project_id
    )
    return int((await session.execute(stmt)).scalar_one())


async def org_month_cost_cents(session: AsyncSession, *, organization_id: uuid.UUID) -> int:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.coalesce(func.sum(CreativeCostEvent.cost_cents), 0))
        .where(CreativeCostEvent.organization_id == organization_id)
        .where(CreativeCostEvent.occurred_at >= start)
    )
    return int((await session.execute(stmt)).scalar_one())


async def org_budget_exceeded(
    session: AsyncSession, *, organization_id: uuid.UUID, add_cents: int = 0
) -> bool:
    """True if this org's month-to-date creative spend (+ a proposed add)
    would exceed its monthly budget cap. 0 cap = unbounded (use plan default
    later). Pure read — caller decides whether to block."""
    cap = get_settings().video_org_monthly_budget_cents
    if cap <= 0:
        return False
    spent = await org_month_cost_cents(session, organization_id=organization_id)
    return (spent + add_cents) > cap
