"""Connector sync orchestration — writes real metrics only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.connectors import upsert_metric
from aicmo.modules.advisor.connectors_models import ConnectorSyncRun
from aicmo.modules.integrations.models import IntegrationConnection


async def sync_brand_connectors(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
) -> int:
    """Sync all connected integrations for a brand. Returns rows pulled."""
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.brand_id == brand_id,
        IntegrationConnection.state == "ACTIVE",
        IntegrationConnection.provider_slug.in_(
            [
                "instagram_organic",
                "facebook_pages",
                "google_business_profile",
                "linkedin_organic",
                "youtube",
                "pinterest",
            ]
        ),
    )
    connections = (await session.execute(stmt)).scalars().all()
    total = 0
    for conn in connections:
        pulled = await _sync_connection(session, connection=conn)
        total += pulled
    if total:
        await session.commit()
    return total


async def _sync_connection(
    session: AsyncSession,
    *,
    connection: IntegrationConnection,
) -> int:
    """Provider-specific sync. Returns 0 until OAuth sync is implemented."""
    started = datetime.now(UTC)
    run = ConnectorSyncRun(
        id=uuid.uuid4(),
        brand_id=connection.brand_id,  # type: ignore[arg-type]
        connection_id=connection.id,
        provider_slug=connection.provider_slug,
        status="success",
        rows_pulled=0,
        started_at=started,
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    connection.last_sync_at = datetime.now(UTC)
    return 0
