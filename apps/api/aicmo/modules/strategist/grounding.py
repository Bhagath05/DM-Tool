"""Phase 7.15/7.16 — ground marketing strategy in the brand's belief memory.

Thin wrapper over the shared ``belief.grounding`` foundation (Phase 7.16), so the
Strategist, Advisor and Opportunity engines all ground the SAME way over the SAME
evidence-graded belief memory — no duplicate grounding logic. Kept as a named
strategist entry point for the router + tests.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief import grounding as belief_grounding
from aicmo.modules.belief.grounding import EvidenceGrounding
from aicmo.tenancy.context import TenantContext


async def resolve_strategy_evidence(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[str, EvidenceGrounding]:
    """Return ``(prompt_block, provenance)`` grounding strategy in the brand's
    evidence-graded beliefs. Brand-scoped; degrades to INSUFFICIENT_EVIDENCE."""
    return await belief_grounding.resolve_evidence_grounding(session, tenant=tenant)
