"""Trends business logic.

Key cost-control rule: REFRESH_COOLDOWN_SECONDS. Any refresh inside that
window returns the existing row instead of triggering another collector +
Gemini call. This protects against double-clicks and accidental polling.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.trends.models import TrendReport
from aicmo.modules.trends.schemas import TrendReportResponse
from aicmo.tenancy.context import TenantContext

REFRESH_COOLDOWN_SECONDS = 60 * 60  # 1h


async def get_report(
    session: AsyncSession, brand_id: uuid.UUID
) -> TrendReport | None:
    stmt = select(TrendReport).where(TrendReport.brand_id == brand_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def require_report(
    session: AsyncSession, brand_id: uuid.UUID
) -> TrendReport:
    report = await get_report(session, brand_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trend report yet — call POST /trends/refresh",
        )
    return report


async def start_refresh(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[TrendReportResponse, bool]:
    """Create or reset the brand's trend report row to status='pending'."""
    existing = await get_report(session, tenant.brand_id)

    if existing and existing.status == "pending":
        return _to_response(existing), False

    if existing and _within_cooldown(existing.updated_at):
        return _to_response(existing), False

    if existing is None:
        report = TrendReport(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            status="pending",
            raw_trends=None,
            analysis=None,
            analysis_error=None,
        )
        session.add(report)
    else:
        existing.status = "pending"
        existing.raw_trends = None
        existing.analysis = None
        existing.analysis_error = None
        report = existing

    await session.commit()
    await session.refresh(report)
    return _to_response(report), True


def _within_cooldown(updated_at: datetime) -> bool:
    age = datetime.now(UTC) - updated_at
    return age < timedelta(seconds=REFRESH_COOLDOWN_SECONDS)


def _to_response(report: TrendReport) -> TrendReportResponse:
    return TrendReportResponse.model_validate(report)
