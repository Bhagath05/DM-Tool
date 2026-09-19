"""Business Brain — evidence kinds, ingestion, ICP honesty, SSRF categorization."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from aicmo.modules.business_brain.ingestion import ingest_research_result
from aicmo.modules.business_brain.providers.local_website import (
    LocalWebsiteResearchProvider,
    _evidence_from_signals,
)
from aicmo.modules.business_brain.providers.null import NullWebsiteResearchProvider
from aicmo.modules.business_brain.schemas import (
    EvidenceCandidate,
    ResearchResult,
    StartWebsiteResearchRequest,
)


def test_start_request_requires_url() -> None:
    with pytest.raises(ValidationError):
        StartWebsiteResearchRequest(website_url="")


@pytest.mark.asyncio
async def test_null_provider_is_honest_not_configured() -> None:
    result = await NullWebsiteResearchProvider().research(url="https://example.com")
    assert result.status == "failed"
    assert result.error_category == "NOT_CONFIGURED"
    assert result.evidence == []


@pytest.mark.asyncio
async def test_null_provider_unavailable() -> None:
    result = await NullWebsiteResearchProvider(reason="PROVIDER_UNAVAILABLE").research(
        url="https://example.com"
    )
    assert result.error_category == "PROVIDER_UNAVAILABLE"
    assert not result.evidence


def test_signals_produce_facts_and_observations_not_hypotheses() -> None:
    signals = {
        "title": "Acme Identity Platform",
        "meta_description": "Identity management for mid-market SaaS.",
        "headings": ["Secure access", "For security teams"],
        "schema_types": ["Organization", "SoftwareApplication"],
        "social_links": {"linkedin": "https://linkedin.com/company/acme"},
    }
    items = _evidence_from_signals(signals, "https://acme.example")
    kinds = {i.kind for i in items}
    assert "fact" in kinds or "observation" in kinds
    assert "hypothesis" not in kinds  # signal path never invents hypotheses


@pytest.mark.asyncio
async def test_ingestion_never_promotes_llm_fact_to_fact() -> None:
    """LLM-sourced 'fact' candidates are coerced to hypothesis."""
    session = AsyncMock()
    session.add = lambda *_a, **_k: None
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    result = ResearchResult(
        status="completed",
        provider="test",
        final_url="https://acme.example",
        sources=["https://acme.example"],
        evidence=[
            EvidenceCandidate(
                kind="fact",
                category="audience",
                claim="Security leaders are the buyers.",
                confidence=80,
                source_type="llm",
                source_url="https://acme.example",
            )
        ],
    )
    rows = await ingest_research_result(
        session,
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        research_job_id=uuid.uuid4(),
        result=result,
    )
    assert len(rows) == 1
    assert rows[0].kind == "hypothesis"


@pytest.mark.asyncio
async def test_local_provider_maps_unsafe_fetch_to_unsafe_url() -> None:
    from aicmo.modules.discovery.fetcher import DiscoveryFetchError

    provider = LocalWebsiteResearchProvider()
    with patch(
        "aicmo.modules.business_brain.providers.local_website.fetcher.fetch_website",
        new=AsyncMock(side_effect=DiscoveryFetchError("Host resolves to a private IP")),
    ):
        result = await provider.research(url="http://127.0.0.1")
    assert result.status == "failed"
    assert result.error_category == "UNSAFE_URL"
    assert result.evidence == []


@pytest.mark.asyncio
async def test_local_provider_insufficient_when_empty_signals() -> None:
    provider = LocalWebsiteResearchProvider()
    with (
        patch(
            "aicmo.modules.business_brain.providers.local_website.fetcher.fetch_website",
            new=AsyncMock(return_value=("https://empty.example", "<html></html>")),
        ),
        patch(
            "aicmo.modules.business_brain.providers.local_website.fetcher.extract_signals",
            return_value={},
        ),
    ):
        result = await provider.research(url="https://empty.example")
    assert result.status == "failed"
    assert result.error_category == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_icp_generate_refuses_without_grounded_evidence() -> None:
    from aicmo.modules.business_brain import icp_service

    tenant = SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        user_uuid=uuid.uuid4(),
    )
    session = AsyncMock()
    # scalars().all() empty
    result_proxy = SimpleNamespace(all=lambda: [])
    session.scalars = AsyncMock(return_value=result_proxy)

    out = await icp_service.generate_icps(session, tenant=tenant)  # type: ignore[arg-type]
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert out.items == []
