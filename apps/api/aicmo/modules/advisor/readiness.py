"""Minimum data threshold before generating recommendations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.modules.leads.models import Lead
from aicmo.modules.onboarding.schemas import BusinessProfileResponse


async def assess_readiness(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    signal_count: int,
) -> tuple[bool, list[str], str | None]:
    """Returns (ready, setup_steps, message)."""
    brand_id = profile.brand_id

    lead_count = (
        await session.execute(
            select(func.count()).select_from(Lead).where(Lead.brand_id == brand_id)
        )
    ).scalar_one()

    content_count = (
        await session.execute(
            select(func.count())
            .select_from(GeneratedContent)
            .where(GeneratedContent.brand_id == brand_id)
        )
    ).scalar_one()

    ad_count = (
        await session.execute(
            select(func.count())
            .select_from(GeneratedAd)
            .where(GeneratedAd.brand_id == brand_id)
        )
    ).scalar_one()

    integration_count = (
        await session.execute(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(IntegrationConnection.brand_id == brand_id)
        )
    ).scalar_one()

    activity_signals = sum(
        1
        for n in (lead_count, content_count, ad_count, integration_count)
        if n and n > 0
    )

    has_profile = profile.analysis is not None
    total_signals = signal_count + activity_signals + (1 if has_profile else 0)

    if total_signals >= 3 and (activity_signals >= 1 or lead_count > 0):
        return True, [], None

    steps: list[str] = []
    if integration_count == 0:
        steps.extend(
            [
                "Connect Instagram",
                "Connect Facebook",
                "Connect Google Business",
            ]
        )
    if content_count == 0 and ad_count == 0:
        steps.append("Create your first campaign")
    if lead_count == 0:
        steps.append("Publish a lead page and share its link")

    message = "Not enough business activity data yet."
    return False, steps, message
