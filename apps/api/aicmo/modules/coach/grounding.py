"""Phase 7.17/7.18 — the AI Coach's thin, defensive hook into the shared belief
grounding (``belief.grounding``). It does NOT create a memory system: it reads
the brand's evidence-graded beliefs and returns both the prompt block each Coach
surface injects (7.17) and the structured ``EvidenceGrounding`` provenance the
Coach attaches to its responses (7.18). Defensive by design — a grounding miss
must never break an advisory Coach response; it degrades to an empty block (which
the prompt renders as INSUFFICIENT_EVIDENCE) and ``None`` provenance. Belief
access is read-only and brand-scoped by the server-derived TenantContext; it
grants no authorization and writes no belief. Provenance is server-derived — the
LLM never creates or modifies it.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief.grounding import EvidenceGrounding, resolve_evidence_grounding
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def resolve_coach_evidence(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[str, EvidenceGrounding | None]:
    """Return ``(prompt_block, provenance)`` for a Coach surface.

    ``prompt_block`` is injected into the LLM prompt; ``provenance`` is the
    server-derived ``EvidenceGrounding`` attached to the Coach response so the
    recommendation is traceable to the beliefs that supported it. Degrades to
    ``("", None)`` on any failure — advisory Coach calls must never break, and a
    missing grounding is surfaced honestly rather than fabricated.
    """
    try:
        return await resolve_evidence_grounding(session, tenant=tenant)
    except Exception as e:
        log.warning("coach.belief_grounding_failed", error=str(e)[:200])
        return "", None


async def coach_belief_block(session: AsyncSession, *, tenant: TenantContext) -> str:
    """Return the brand's evidence-graded belief prompt block, or "" on any
    failure (never raises — advisory Coach calls must degrade gracefully)."""
    block, _grounding = await resolve_coach_evidence(session, tenant=tenant)
    return block


async def coach_economics_block(session: AsyncSession, *, tenant: TenantContext) -> str:
    """Phase 7.20 Stage 3b.1 — the brand's Business Economics as a deterministic,
    provenance-tagged prompt block, or "" when nothing is captured or on any
    failure (never raises — advisory Coach calls must degrade gracefully).

    Reuses the canonical, facet-scoped ``get_business_dna.get_economics_facet``
    (no full-DNA build, no duplicated composition). Brand-scoped via TenantContext;
    read-only. Each line keeps its server-derived provenance tier so the LLM can
    tell owner-stated/verified figures from derived ones and never upgrades them.
    """
    try:
        from aicmo.modules.business_dna.service import get_economics_facet, render_economics_block

        facet = await get_economics_facet(session, tenant=tenant)
    except Exception as e:
        log.warning("coach.economics_facet_failed", error=str(e)[:200])
        return ""
    return render_economics_block(facet)
