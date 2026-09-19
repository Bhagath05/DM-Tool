"""Local competitor research — evidence / provided URLs only.

Never invents competitor companies, headcount, revenue, or market share.
Uses discovery.fetcher for any optional competitor URL fetches (SSRF-safe).
"""

from __future__ import annotations

from urllib.parse import urlparse

from aicmo.modules.business_brain.schemas import EvidenceCandidate, ResearchResult
from aicmo.modules.discovery import fetcher

_SNIPPET_MAX = 400
_MAX_COMPETITOR_URLS = 5


def _snip(text: str | None) -> str | None:
    if not text:
        return None
    t = " ".join(str(text).split())
    return t[:_SNIPPET_MAX] if t else None


def _host_label(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return host or url[:80]
    except Exception:
        return url[:80]


class LocalCompetitorResearchProvider:
    """Derive competitor *candidates* from supplied URLs + grounded context."""

    name = "local_competitor"

    async def research_competitors(
        self,
        *,
        business_website: str | None,
        grounded_claims: list[str],
        competitor_urls: list[str],
    ) -> ResearchResult:
        urls = [u.strip() for u in competitor_urls if u and u.strip()][
            :_MAX_COMPETITOR_URLS
        ]
        if not urls:
            # Without explicit competitor URLs we refuse to invent a list.
            if len(grounded_claims) < 2:
                return ResearchResult(
                    status="failed",
                    error_category="INSUFFICIENT_EVIDENCE",
                    error_message=(
                        "Need website facts/observations and at least one "
                        "competitor website URL. No competitors were fabricated."
                    ),
                    provider=self.name,
                    result_summary={
                        "candidates": [],
                        "status": "INSUFFICIENT_EVIDENCE",
                    },
                )
            return ResearchResult(
                status="failed",
                error_category="INSUFFICIENT_EVIDENCE",
                error_message=(
                    "Competitor research requires competitor website URLs "
                    "(we do not invent competitor companies from thin air)."
                ),
                provider=self.name,
                final_url=business_website,
                result_summary={
                    "candidates": [],
                    "status": "INSUFFICIENT_EVIDENCE",
                },
            )

        evidence: list[EvidenceCandidate] = []
        candidates: list[dict] = []
        sources: list[str] = []
        failures = 0

        for raw in urls:
            try:
                final_url, html = await fetcher.fetch_website(raw)
            except fetcher.DiscoveryFetchError as e:
                failures += 1
                msg = str(e)
                category = "UNSAFE_URL" if _looks_unsafe(msg) else "RESEARCH_FAILED"
                evidence.append(
                    EvidenceCandidate(
                        kind="observation",
                        category="marketing",
                        claim=(
                            f"Could not research competitor URL “{raw[:120]}”: "
                            f"{msg[:200]}"
                        ),
                        confidence=20,
                        source_url=raw[:500],
                        source_type="website",
                        snippet=_snip(msg),
                        claim_key=f"competitor-error:{_host_label(raw)}"[:160],
                    )
                )
                candidates.append(
                    {
                        "name": _host_label(raw),
                        "reason": f"Fetch failed ({category}).",
                        "source_url": raw[:500],
                        "confidence": 10,
                        "status": "unknown",
                        "evidence_kinds": ["observation"],
                    }
                )
                continue

            signals = fetcher.extract_signals(html, final_url)
            title = (signals.get("title") or "").strip() or _host_label(final_url)
            meta = (
                signals.get("meta_description")
                or signals.get("og_description")
                or ""
            ).strip()
            sources.append(final_url)

            reason_bits = [
                f"Public website “{title[:120]}” was supplied as a competitor URL."
            ]
            if meta:
                reason_bits.append(f"It describes itself as: {meta[:180]}")
            if business_website:
                reason_bits.append(
                    "Treated as a candidate only — not a verified competitor "
                    "relationship."
                )
            reason = " ".join(reason_bits)

            evidence.append(
                EvidenceCandidate(
                    kind="observation",
                    category="marketing",
                    claim=(
                        f"Competitor candidate “{title[:160]}” observed at "
                        f"{final_url}."
                    ),
                    confidence=65,
                    source_url=final_url,
                    source_type="website",
                    snippet=_snip(meta or title),
                    claim_key=f"competitor:{_host_label(final_url)}"[:160],
                )
            )
            evidence.append(
                EvidenceCandidate(
                    kind="hypothesis",
                    category="marketing",
                    claim=(
                        f"Hypothesis: “{title[:120]}” may compete with this "
                        f"business because a user-supplied URL was researched. "
                        f"{reason[:400]}"
                    ),
                    confidence=40,
                    source_url=final_url,
                    source_type="derived",
                    snippet=_snip(reason),
                    claim_key=f"competitor-hyp:{_host_label(final_url)}"[:160],
                )
            )
            candidates.append(
                {
                    "name": title[:160],
                    "reason": reason[:500],
                    "source_url": final_url,
                    "confidence": 55,
                    "status": "candidate",
                    "evidence_kinds": ["observation", "hypothesis"],
                }
            )

        if not candidates:
            return ResearchResult(
                status="failed",
                error_category="RESEARCH_FAILED",
                error_message="No competitor URLs could be researched.",
                provider=self.name,
                result_summary={"candidates": [], "status": "RESEARCH_FAILED"},
            )

        partial = failures > 0 or len(candidates) < len(urls)
        return ResearchResult(
            status="partial" if partial else "completed",
            error_category="PARTIAL_EVIDENCE" if partial else None,
            error_message=(
                "Some competitor URLs could not be researched." if partial else None
            ),
            provider=self.name,
            final_url=business_website,
            sources=sources,
            evidence=evidence,
            result_summary={
                "candidates": candidates,
                "status": "partial" if partial else "ok",
            },
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


def get_competitor_research_provider() -> LocalCompetitorResearchProvider:
    return LocalCompetitorResearchProvider()
