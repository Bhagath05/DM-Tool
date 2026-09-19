"""Research provider protocols — website, competitor, market."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aicmo.modules.business_brain.schemas import ResearchResult


@runtime_checkable
class WebsiteResearchProvider(Protocol):
    name: str

    async def research(self, *, url: str) -> ResearchResult:
        """Research a public website. Must never fabricate business facts."""
        ...


@runtime_checkable
class CompetitorResearchProvider(Protocol):
    name: str

    async def research_competitors(
        self,
        *,
        business_website: str | None,
        grounded_claims: list[str],
        competitor_urls: list[str],
    ) -> ResearchResult:
        """Identify competitor *candidates* from evidence / provided URLs only.

        Must never invent competitor companies, market share, or headcount.
        """
        ...


@runtime_checkable
class MarketResearchProvider(Protocol):
    name: str

    async def research_market(
        self,
        *,
        business_website: str | None,
        industry: str | None,
        grounded_claims: list[str],
    ) -> ResearchResult:
        """Collect market signals from grounded evidence only.

        Must never invent market size, growth %, revenue, or demand scores.
        """
        ...
