"""Tenant isolation + research job helpers for Business Brain."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from aicmo.modules.business_brain import research_service
from aicmo.modules.business_brain.models import BrainResearchJob
from aicmo.modules.business_brain.schemas import (
    ResearchResult,
    StartWebsiteResearchRequest,
)


def _tenant(brand: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=brand if brand is not None else uuid.uuid4(),
        user_uuid=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_get_job_rejects_cross_brand() -> None:
    brand_a = uuid.uuid4()
    brand_b = uuid.uuid4()
    job_id = uuid.uuid4()
    row = BrainResearchJob(
        id=job_id,
        organization_id=uuid.uuid4(),
        brand_id=brand_a,
        created_by_user_id=uuid.uuid4(),
        kind="website",
        input_url="https://a.example",
        normalized_url="https://a.example",
        status="completed",
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)
    tenant = _tenant(brand_b)
    with pytest.raises(HTTPException) as ei:
        await research_service.get_job(session, tenant=tenant, job_id=job_id)  # type: ignore[arg-type]
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_start_reuses_active_job() -> None:
    brand = uuid.uuid4()
    existing_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=existing_id,
        status="running",
        brand_id=brand,
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=existing)
    session.add = lambda *a, **k: None
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    tenant = _tenant(brand)
    out = await research_service.start_website_research(
        session,
        tenant=tenant,  # type: ignore[arg-type]
        payload=StartWebsiteResearchRequest(website_url="https://acme.example"),
    )
    assert out.reused_existing is True
    assert out.id == existing_id
    assert out.status == "running"


@pytest.mark.asyncio
async def test_start_requires_brand() -> None:
    session = AsyncMock()
    tenant = _tenant(None)
    tenant.brand_id = None
    with pytest.raises(HTTPException) as ei:
        await research_service.start_website_research(
            session,
            tenant=tenant,  # type: ignore[arg-type]
            payload=StartWebsiteResearchRequest(website_url="https://acme.example"),
        )
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_skips_when_claim_loses() -> None:
    """Second worker must not fetch/ingest when status is no longer queued."""
    job_id = uuid.uuid4()
    org = uuid.uuid4()
    brand = uuid.uuid4()

    claim_result = SimpleNamespace(one_or_none=lambda: None)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=claim_result)
    session.commit = AsyncMock()
    session.get = AsyncMock(
        return_value=BrainResearchJob(
            id=job_id,
            organization_id=org,
            brand_id=brand,
            created_by_user_id=uuid.uuid4(),
            kind="website",
            input_url="https://acme.example",
            normalized_url="https://acme.example",
            status="running",
        )
    )

    with patch(
        "aicmo.modules.business_brain.research_service.get_website_research_provider"
    ) as provider_factory:
        await research_service.execute_research_job(
            session,
            job_id=job_id,
            organization_id=org,
            brand_id=brand,
        )
        provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_execute_claims_queued_then_runs_provider() -> None:
    job_id = uuid.uuid4()
    org = uuid.uuid4()
    brand = uuid.uuid4()
    claimed = SimpleNamespace(
        normalized_url="https://acme.example",
        kind="website",
        result_summary=None,
    )
    claim_result = SimpleNamespace(one_or_none=lambda: claimed)

    running_row = BrainResearchJob(
        id=job_id,
        organization_id=org,
        brand_id=brand,
        created_by_user_id=uuid.uuid4(),
        kind="website",
        input_url="https://acme.example",
        normalized_url="https://acme.example",
        status="running",
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=claim_result)
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=running_row)
    session.add = lambda *a, **k: None
    session.flush = AsyncMock()

    provider = AsyncMock()
    provider.research = AsyncMock(
        return_value=ResearchResult(
            status="failed",
            error_category="INSUFFICIENT_EVIDENCE",
            error_message="empty",
            provider="local_website",
            evidence=[],
        )
    )

    with patch(
        "aicmo.modules.business_brain.research_service.get_website_research_provider",
        return_value=provider,
    ):
        await research_service.execute_research_job(
            session,
            job_id=job_id,
            organization_id=org,
            brand_id=brand,
        )

    provider.research.assert_awaited_once_with(url="https://acme.example")
    assert running_row.status == "failed"
