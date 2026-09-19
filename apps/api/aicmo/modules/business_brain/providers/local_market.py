"""Local market research — grounded evidence only.

Never invents market size, growth %, revenue, share, demand scores, or
customer counts. Optional LLM enrichment stays hypothesis-labeled.
"""

from __future__ import annotations

from aicmo.modules.business_brain.schemas import EvidenceCandidate, ResearchResult

_SNIPPET_MAX = 400
_MIN_GROUNDED = 2


def _snip(text: str | None) -> str | None:
    if not text:
        return None
    t = " ".join(str(text).split())
    return t[:_SNIPPET_MAX] if t else None


class LocalMarketResearchProvider:
    name = "local_market"

    async def research_market(
        self,
        *,
        business_website: str | None,
        industry: str | None,
        grounded_claims: list[str],
    ) -> ResearchResult:
        claims = [c.strip() for c in grounded_claims if c and c.strip()]
        if len(claims) < _MIN_GROUNDED:
            return ResearchResult(
                status="failed",
                error_category="INSUFFICIENT_EVIDENCE",
                error_message=(
                    "Need at least two website facts/observations before "
                    "market signals can be proposed. No market metrics were "
                    "fabricated."
                ),
                provider=self.name,
                final_url=business_website,
                result_summary={"signals": [], "status": "INSUFFICIENT_EVIDENCE"},
            )

        evidence: list[EvidenceCandidate] = []
        signals: list[dict] = []
        sources = [business_website] if business_website else []

        if industry and industry.strip():
            claim = (
                f"Observed industry/category context from Brand Brain: "
                f"{industry.strip()[:200]}."
            )
            evidence.append(
                EvidenceCandidate(
                    kind="observation",
                    category="market",
                    claim=claim,
                    confidence=70,
                    source_url=business_website,
                    source_type="profile",
                    snippet=_snip(industry),
                    claim_key="market:category",
                )
            )
            signals.append(
                {
                    "signal_kind": "category",
                    "claim": claim,
                    "evidence_kind": "observation",
                    "confidence": 70,
                    "source_url": business_website,
                    "source_type": "profile",
                }
            )

        # Surface grounded website claims as market-relevant observations —
        # still observations, never inflated into market statistics.
        for i, text in enumerate(claims[:6]):
            claim = (
                f"Market-relevant observation from existing research: "
                f"{text[:400]}"
            )
            evidence.append(
                EvidenceCandidate(
                    kind="observation",
                    category="market",
                    claim=claim,
                    confidence=60,
                    source_url=business_website,
                    source_type="website",
                    snippet=_snip(text),
                    claim_key=f"market:grounded:{i}",
                )
            )
            signals.append(
                {
                    "signal_kind": "positioning",
                    "claim": claim,
                    "evidence_kind": "observation",
                    "confidence": 60,
                    "source_url": business_website,
                    "source_type": "website",
                }
            )

        hyp = await _maybe_market_hypotheses(claims, business_website)
        for item in hyp:
            evidence.append(item)
            signals.append(
                {
                    "signal_kind": "pain_point"
                    if "pain" in item.claim.lower()
                    else "trend",
                    "claim": item.claim,
                    "evidence_kind": item.kind,
                    "confidence": item.confidence,
                    "source_url": item.source_url,
                    "source_type": item.source_type,
                }
            )

        partial = len(signals) < 3
        return ResearchResult(
            status="partial" if partial else "completed",
            error_category="PARTIAL_EVIDENCE" if partial else None,
            error_message=(
                "Only limited market signals could be derived from existing "
                "evidence."
                if partial
                else None
            ),
            provider=self.name,
            final_url=business_website,
            sources=sources,
            evidence=evidence,
            result_summary={
                "signals": signals,
                "status": "partial" if partial else "ok",
            },
        )


async def _maybe_market_hypotheses(
    claims: list[str],
    business_website: str | None,
) -> list[EvidenceCandidate]:
    """Optional LLM hypotheses — never facts, never invented metrics."""
    if len(claims) < 2:
        return []
    try:
        from pydantic import BaseModel, Field

        from aicmo.llm import get_llm_router
        from aicmo.llm.providers.base import LLMMessage

        class _Item(BaseModel):
            claim: str
            confidence: int = Field(ge=0, le=55)

        class _Out(BaseModel):
            items: list[_Item] = Field(default_factory=list)

        bullet = "\n".join(f"- {c[:200]}" for c in claims[:10])
        prompt = (
            "Given ONLY these grounded marketing claims, propose 0-2 market "
            "HYPOTHESES about customer pains or positioning alternatives. "
            "Do NOT invent market size, growth rates, revenue, market share, "
            "demand scores, or customer counts. If evidence is weak, return "
            "an empty items list.\n\n"
            f"Website: {business_website or 'unknown'}\nClaims:\n{bullet}\n"
        )
        router = get_llm_router()
        result = await router.generate(
            response_schema=_Out,
            system=(
                "You are a careful market researcher. Every claim you produce "
                "is a hypothesis, never a fact. Never invent statistics."
            ),
            messages=[LLMMessage(role="user", content=prompt)],
            task="business_research",
            temperature=0.3,
            max_tokens=900,
        )
        out: list[EvidenceCandidate] = []
        for item in result.data.items[:2]:
            claim = (item.claim or "").strip()
            if len(claim) < 8:
                continue
            # Hard reject metric-looking hallucinations.
            lower = claim.lower()
            if any(
                tok in lower
                for tok in (
                    "billion",
                    "million customers",
                    "market share",
                    "cagr",
                    "% growth",
                    "tam ",
                    "sam ",
                    "som ",
                )
            ):
                continue
            out.append(
                EvidenceCandidate(
                    kind="hypothesis",
                    category="market",
                    claim=f"Hypothesis: {claim[:900]}",
                    confidence=min(55, max(0, int(item.confidence))),
                    source_url=business_website,
                    source_type="llm",
                    snippet=_snip(claim),
                    claim_key=f"market:hyp:{len(out)}",
                )
            )
        return out
    except Exception:
        return []


def get_market_research_provider() -> LocalMarketResearchProvider:
    return LocalMarketResearchProvider()
