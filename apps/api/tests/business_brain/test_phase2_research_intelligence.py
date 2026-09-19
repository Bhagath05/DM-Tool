"""Phase 2 — competitor/market providers, evidence integrity, anti-fabrication."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.business_brain.ingestion import ingest_research_result
from aicmo.modules.business_brain.providers.local_competitor import (
    LocalCompetitorResearchProvider,
)
from aicmo.modules.business_brain.providers.local_market import (
    LocalMarketResearchProvider,
)
from aicmo.modules.business_brain.providers.null import (
    NullCompetitorResearchProvider,
    NullMarketResearchProvider,
)
from aicmo.modules.business_brain.schemas import (
    EvidenceCandidate,
    ResearchResult,
)


@pytest.mark.asyncio
async def test_null_competitor_is_honest() -> None:
    result = await NullCompetitorResearchProvider().research_competitors(
        business_website="https://acme.example",
        grounded_claims=["a", "b"],
        competitor_urls=[],
    )
    assert result.status == "failed"
    assert result.error_category == "NOT_CONFIGURED"
    assert result.evidence == []
    assert result.result_summary is not None
    assert result.result_summary["candidates"] == []


@pytest.mark.asyncio
async def test_null_market_unavailable() -> None:
    result = await NullMarketResearchProvider(reason="PROVIDER_UNAVAILABLE").research_market(
        business_website=None,
        industry=None,
        grounded_claims=[],
    )
    assert result.error_category == "PROVIDER_UNAVAILABLE"
    assert not result.evidence


@pytest.mark.asyncio
async def test_competitor_refuses_without_urls() -> None:
    result = await LocalCompetitorResearchProvider().research_competitors(
        business_website="https://acme.example",
        grounded_claims=["Title is Acme", "Meta describes SaaS"],
        competitor_urls=[],
    )
    assert result.status == "failed"
    assert result.error_category == "INSUFFICIENT_EVIDENCE"
    assert result.evidence == []
    assert "fabricat" in (result.error_message or "").lower() or "invent" in (
        result.error_message or ""
    ).lower()


@pytest.mark.asyncio
async def test_competitor_evidence_backed_from_url() -> None:
    provider = LocalCompetitorResearchProvider()
    with (
        patch(
            "aicmo.modules.business_brain.providers.local_competitor.fetcher.fetch_website",
            new=AsyncMock(
                return_value=(
                    "https://rival.example",
                    "<html><title>Rival Co</title></html>",
                )
            ),
        ),
        patch(
            "aicmo.modules.business_brain.providers.local_competitor.fetcher.extract_signals",
            return_value={
                "title": "Rival Co",
                "meta_description": "Identity for startups",
            },
        ),
    ):
        result = await provider.research_competitors(
            business_website="https://acme.example",
            grounded_claims=["Acme sells identity"],
            competitor_urls=["https://rival.example"],
        )
    assert result.status == "completed"
    assert result.result_summary is not None
    candidates = result.result_summary["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["status"] == "candidate"
    assert candidates[0]["name"] == "Rival Co"
    kinds = {e.kind for e in result.evidence}
    assert "observation" in kinds
    assert "hypothesis" in kinds
    assert "fact" not in kinds or all(
        e.source_type != "llm" for e in result.evidence if e.kind == "fact"
    )


@pytest.mark.asyncio
async def test_market_insufficient_without_grounded() -> None:
    result = await LocalMarketResearchProvider().research_market(
        business_website="https://acme.example",
        industry="SaaS",
        grounded_claims=["only one"],
    )
    assert result.status == "failed"
    assert result.error_category == "INSUFFICIENT_EVIDENCE"
    assert result.evidence == []


@pytest.mark.asyncio
async def test_market_signals_are_observations_or_hypotheses() -> None:
    with patch(
        "aicmo.modules.business_brain.providers.local_market._maybe_market_hypotheses",
        new=AsyncMock(return_value=[]),
    ):
        result = await LocalMarketResearchProvider().research_market(
            business_website="https://acme.example",
            industry="B2B SaaS",
            grounded_claims=[
                "The website title is Acme",
                "Homepage describes identity management",
            ],
        )
    assert result.status in ("completed", "partial")
    assert result.evidence
    assert all(e.kind in ("observation", "hypothesis") for e in result.evidence)
    # Never invent market size style facts
    joined = " ".join(e.claim.lower() for e in result.evidence)
    assert "market share" not in joined
    assert "billion" not in joined


@pytest.mark.asyncio
async def test_ingestion_contradiction_keeps_prior_row() -> None:
    """Same claim_key + different claim → prior marked contradicted, not overwritten."""
    brand = uuid.uuid4()
    org = uuid.uuid4()
    job = uuid.uuid4()

    prior = SimpleNamespace(
        claim="Old claim about category",
        status="active",
        superseded_by_id=None,
    )

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=prior)
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = ResearchResult(
        status="completed",
        provider="test",
        final_url="https://acme.example",
        evidence=[
            EvidenceCandidate(
                kind="observation",
                category="market",
                claim="New conflicting claim about category",
                confidence=70,
                source_type="website",
                claim_key="market:category",
            )
        ],
    )
    rows = await ingest_research_result(
        session,
        organization_id=org,
        brand_id=brand,
        research_job_id=job,
        result=result,
    )
    assert len(rows) == 1
    assert prior.status == "contradicted"
    assert prior.superseded_by_id is not None


@pytest.mark.asyncio
async def test_ingestion_duplicate_claim_key_skips() -> None:
    brand = uuid.uuid4()
    prior = MagicMock()
    prior.claim = "Same claim text"
    prior.status = "active"

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=prior)
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = ResearchResult(
        status="completed",
        provider="test",
        evidence=[
            EvidenceCandidate(
                kind="observation",
                category="market",
                claim="Same claim text",
                confidence=70,
                source_type="website",
                claim_key="market:category",
            )
        ],
    )
    rows = await ingest_research_result(
        session,
        organization_id=uuid.uuid4(),
        brand_id=brand,
        research_job_id=uuid.uuid4(),
        result=result,
    )
    assert rows == [prior]
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_job_still_rejects_cross_brand() -> None:
    from fastapi import HTTPException

    from aicmo.modules.business_brain import research_service
    from aicmo.modules.business_brain.models import BrainResearchJob

    brand_a = uuid.uuid4()
    brand_b = uuid.uuid4()
    job_id = uuid.uuid4()
    row = BrainResearchJob(
        id=job_id,
        organization_id=uuid.uuid4(),
        brand_id=brand_a,
        created_by_user_id=uuid.uuid4(),
        kind="competitor",
        input_url="https://a.example",
        normalized_url="competitor:https://a.example",
        status="completed",
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)
    tenant = SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=brand_b,
        user_uuid=uuid.uuid4(),
    )
    with pytest.raises(HTTPException) as ei:
        await research_service.get_job(session, tenant=tenant, job_id=job_id)  # type: ignore[arg-type]
    assert ei.value.status_code == 404
