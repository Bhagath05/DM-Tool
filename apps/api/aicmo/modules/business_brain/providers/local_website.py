"""Local website research — reuses discovery fetcher (SSRF-safe).

Extracts bounded FACT / OBSERVATION evidence from page signals.
Optional LLM step may add HYPOTHESIS / RECOMMENDATION only when labeled;
never invents facts when the page is empty.
"""

from __future__ import annotations

from aicmo.modules.business_brain.schemas import EvidenceCandidate, ResearchResult
from aicmo.modules.discovery import fetcher

_SNIPPET_MAX = 400


def _snip(text: str | None) -> str | None:
    if not text:
        return None
    t = " ".join(str(text).split())
    if not t:
        return None
    return t[:_SNIPPET_MAX]


class LocalWebsiteResearchProvider:
    """Concrete provider backed by discovery.fetcher — no second fetch stack."""

    name = "local_website"

    async def research(self, *, url: str) -> ResearchResult:
        try:
            final_url, html = await fetcher.fetch_website(url)
        except fetcher.DiscoveryFetchError as e:
            msg = str(e)
            category = "UNSAFE_URL" if _looks_unsafe(msg) else "RESEARCH_FAILED"
            return ResearchResult(
                status="failed",
                error_category=category,  # type: ignore[arg-type]
                error_message=msg[:400],
                provider=self.name,
            )

        signals = fetcher.extract_signals(html, final_url)
        evidence = _evidence_from_signals(signals, final_url)

        if not evidence:
            return ResearchResult(
                status="failed",
                error_category="INSUFFICIENT_EVIDENCE",
                error_message=(
                    "The website was reachable but did not yield enough "
                    "marketing signals to build a Business Brain."
                ),
                provider=self.name,
                final_url=final_url,
                sources=[final_url],
                evidence=[],
            )

        # Soft enrichment: hypotheses only when we already have facts/observations.
        enriched = await _maybe_llm_hypotheses(signals, final_url, evidence)
        all_evidence = evidence + enriched
        partial = len(evidence) < 3
        return ResearchResult(
            status="partial" if partial else "completed",
            error_category="PARTIAL_EVIDENCE" if partial else None,
            error_message=(
                "Only limited page signals were available." if partial else None
            ),
            provider=self.name,
            final_url=final_url,
            sources=[final_url],
            evidence=all_evidence,
        )


def _looks_unsafe(msg: str) -> bool:
    lower = msg.lower()
    return any(
        tok in lower
        for tok in (
            "private",
            "localhost",
            "loopback",
            "not allowed",
            "blocked",
            "metadata",
            "ssrf",
            "only http",
        )
    )


def _evidence_from_signals(signals: dict, final_url: str) -> list[EvidenceCandidate]:
    out: list[EvidenceCandidate] = []

    title = (signals.get("title") or "").strip()
    if title:
        out.append(
            EvidenceCandidate(
                kind="fact",
                category="business",
                claim=f"The website title is “{title[:200]}”.",
                confidence=90,
                source_url=final_url,
                source_type="website",
                snippet=_snip(title),
            )
        )

    meta = (signals.get("meta_description") or signals.get("og_description") or "").strip()
    if meta:
        out.append(
            EvidenceCandidate(
                kind="observation",
                category="business",
                claim=f"The homepage describes the business as: {meta[:280]}",
                confidence=75,
                source_url=final_url,
                source_type="website",
                snippet=_snip(meta),
            )
        )

    headings = signals.get("headings") or []
    if isinstance(headings, list) and headings:
        joined = "; ".join(str(h) for h in headings[:6] if str(h).strip())
        if joined:
            out.append(
                EvidenceCandidate(
                    kind="observation",
                    category="marketing",
                    claim=f"Primary page headings emphasize: {joined[:400]}",
                    confidence=70,
                    source_url=final_url,
                    source_type="website",
                    snippet=_snip(joined),
                )
            )

    schema_types = signals.get("schema_types") or []
    if isinstance(schema_types, list) and schema_types:
        types = ", ".join(str(t) for t in schema_types[:8])
        out.append(
            EvidenceCandidate(
                kind="fact",
                category="business",
                claim=f"Structured data on the site declares schema types: {types}.",
                confidence=85,
                source_url=final_url,
                source_type="website",
                snippet=_snip(types),
            )
        )

    social = signals.get("social_links") or {}
    if isinstance(social, dict) and social:
        nets = ", ".join(sorted(social.keys())[:8])
        out.append(
            EvidenceCandidate(
                kind="fact",
                category="marketing",
                claim=f"The website links to social profiles on: {nets}.",
                confidence=80,
                source_url=final_url,
                source_type="website",
                snippet=_snip(nets),
            )
        )

    return out


async def _maybe_llm_hypotheses(
    signals: dict,
    final_url: str,
    base: list[EvidenceCandidate],
) -> list[EvidenceCandidate]:
    """Optional LLM hypotheses — labeled as hypothesis/recommendation only."""
    if len(base) < 2:
        return []
    try:
        from pydantic import BaseModel, Field

        from aicmo.llm import get_llm_router
        from aicmo.llm.providers.base import LLMMessage

        class _HypItem(BaseModel):
            kind: str = Field(description="hypothesis or recommendation only")
            category: str
            claim: str
            confidence: int = Field(ge=0, le=70)

        class _HypOut(BaseModel):
            items: list[_HypItem] = Field(default_factory=list)

        facts = "\n".join(f"- [{e.kind}] {e.claim}" for e in base[:12])
        prompt = (
            "Given ONLY these website-derived claims, propose 0-3 ICP/audience "
            "HYPOTHESES or RECOMMENDATIONS. Do NOT invent facts. "
            "If evidence is weak, return an empty items list.\n\n"
            f"Source URL: {final_url}\nClaims:\n{facts}\n"
        )
        router = get_llm_router()
        result = await router.generate(
            response_schema=_HypOut,
            system=(
                "You are a careful marketing researcher. Never state a hypothesis "
                "as a fact. kind must be hypothesis or recommendation."
            ),
            messages=[LLMMessage(role="user", content=prompt)],
            task="business_research",
            temperature=0.3,
            max_tokens=1200,
        )
        out: list[EvidenceCandidate] = []
        for item in result.data.items[:3]:
            kind = (item.kind or "").strip().lower()
            if kind not in ("hypothesis", "recommendation"):
                continue
            cat = (item.category or "audience").strip().lower()
            if cat not in ("business", "audience", "market", "marketing"):
                cat = "audience"
            out.append(
                EvidenceCandidate(
                    kind=kind,  # type: ignore[arg-type]
                    category=cat,  # type: ignore[arg-type]
                    claim=item.claim[:1000],
                    confidence=min(70, max(0, int(item.confidence))),
                    source_url=final_url,
                    source_type="llm",
                    snippet=_snip(item.claim),
                )
            )
        return out
    except Exception:
        # LLM optional — signal-based facts already captured.
        return []


def get_website_research_provider() -> LocalWebsiteResearchProvider:
    """Default provider for Phase 1 — local fetcher reuse."""
    return LocalWebsiteResearchProvider()
