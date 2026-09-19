"""Null providers — honest NOT_CONFIGURED / PROVIDER_UNAVAILABLE."""

from __future__ import annotations

from aicmo.modules.business_brain.schemas import ResearchResult

_ALLOWED = frozenset({"NOT_CONFIGURED", "PROVIDER_UNAVAILABLE"})


class NullWebsiteResearchProvider:
    name = "null"

    def __init__(self, *, reason: str = "NOT_CONFIGURED") -> None:
        self._reason = reason if reason in _ALLOWED else "NOT_CONFIGURED"

    async def research(self, *, url: str) -> ResearchResult:
        return ResearchResult(
            status="failed",
            error_category=self._reason,  # type: ignore[arg-type]
            error_message=(
                "Website research is not configured. "
                "No fabricated Business Brain was produced."
            ),
            provider=self.name,
            sources=[],
            evidence=[],
        )


class NullCompetitorResearchProvider:
    name = "null_competitor"

    def __init__(self, *, reason: str = "NOT_CONFIGURED") -> None:
        self._reason = reason if reason in _ALLOWED else "NOT_CONFIGURED"

    async def research_competitors(
        self,
        *,
        business_website: str | None,
        grounded_claims: list[str],
        competitor_urls: list[str],
    ) -> ResearchResult:
        return ResearchResult(
            status="failed",
            error_category=self._reason,  # type: ignore[arg-type]
            error_message=(
                "Competitor research is not configured. "
                "No competitor companies were fabricated."
            ),
            provider=self.name,
            sources=[],
            evidence=[],
            result_summary={"candidates": [], "status": self._reason},
        )


class NullMarketResearchProvider:
    name = "null_market"

    def __init__(self, *, reason: str = "NOT_CONFIGURED") -> None:
        self._reason = reason if reason in _ALLOWED else "NOT_CONFIGURED"

    async def research_market(
        self,
        *,
        business_website: str | None,
        industry: str | None,
        grounded_claims: list[str],
    ) -> ResearchResult:
        return ResearchResult(
            status="failed",
            error_category=self._reason,  # type: ignore[arg-type]
            error_message=(
                "Market research is not configured. "
                "No market size or growth figures were fabricated."
            ),
            provider=self.name,
            sources=[],
            evidence=[],
            result_summary={"signals": [], "status": self._reason},
        )
