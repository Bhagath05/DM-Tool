"""Phase 7.15/7.16 — ground marketing strategy in the brand's belief memory.

Thin wrapper over the shared ``belief.grounding`` foundation (Phase 7.16), so the
Strategist, Advisor and Opportunity engines all ground the SAME way over the SAME
evidence-graded belief memory — no duplicate grounding logic. Kept as a named
strategist entry point for the router + tests.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief import grounding as belief_grounding
from aicmo.modules.belief.grounding import EvidenceGrounding
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def resolve_strategy_evidence(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[str, EvidenceGrounding]:
    """Return ``(prompt_block, provenance)`` grounding strategy in the brand's
    evidence-graded beliefs. Brand-scoped; degrades to INSUFFICIENT_EVIDENCE."""
    return await belief_grounding.resolve_evidence_grounding(session, tenant=tenant)


async def resolve_strategy_economics(
    session: AsyncSession, *, tenant: TenantContext
) -> str:
    """Phase 7.20 Stage 3b.2 — the brand's Business Economics as a deterministic,
    provenance-tagged prompt block, or "" when nothing is captured / on any
    failure (never raises — strategy generation must degrade gracefully).

    Reuses the canonical, facet-scoped accessor + shared renderer (no duplicate
    Business Economics calculation, no second source of truth). Brand-scoped via
    TenantContext; read-only; the LLM never calculates or upgrades a figure."""
    try:
        from aicmo.modules.business_dna.service import (
            get_economics_facet,
            render_economics_block,
        )

        facet = await get_economics_facet(session, tenant=tenant)
    except Exception as e:
        log.warning("strategist.economics_facet_failed", error=str(e)[:200])
        return ""
    return render_economics_block(facet)
