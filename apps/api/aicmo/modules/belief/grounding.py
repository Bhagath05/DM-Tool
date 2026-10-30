"""Shared evidence-grounding foundation (Phase 7.16).

ONE reusable way to ground a recommendation/strategy/opportunity in the brand's
evidence-graded belief memory — reused by the Strategist (7.15), the Advisor
intelligence engine and the Opportunity engine. It does NOT create another
belief system: it is a thin read over the existing belief resolver.

It returns:
  * ``block`` — a bounded prompt fragment (validated findings + contradictory
    evidence) the generator injects, so the LLM reasons from what the business
    has learned; and
  * ``EvidenceGrounding`` — server-populated provenance (which beliefs, at what
    confidence, plus contradictions) with an explicit ``insufficient_evidence``
    status when the brand holds no validated beliefs.

Honesty is structural: only ACTIVE beliefs count as validated findings;
confidence is the resolver's (freshness-adjusted, server-derived) value — the
LLM never writes it; and an empty memory degrades to INSUFFICIENT_EVIDENCE, so a
recommendation built on it is a hypothesis, not an evidence-backed claim. This
module never writes or modifies a belief, and never grants authorization — the
resolver is strictly brand-scoped by the caller's TenantContext.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief import resolver as belief_resolver
from aicmo.tenancy.context import TenantContext

_MAX_GROUNDING_BELIEFS = 8


class GroundedBelief(BaseModel):
    """One evidence-graded belief that informed a recommendation."""

    category: str
    subject_key: str
    statement: str
    confidence: int = Field(ge=0, le=100)
    evidence_count: int = Field(ge=0)
    status: str = "active"


class EvidenceGrounding(BaseModel):
    """Explainable provenance of the evidence behind a recommendation. ``status``
    is ``insufficient_evidence`` when the brand holds no validated beliefs yet.
    ``contradictions`` are beliefs newer outcomes have called into question."""

    status: str  # "grounded" | "insufficient_evidence"
    belief_count: int = Field(ge=0)
    beliefs: list[GroundedBelief] = Field(default_factory=list)
    contradictions: list[GroundedBelief] = Field(default_factory=list)
    note: str


def _to_grounded(view, *, status: str) -> GroundedBelief:
    conf = view.effective_confidence if view.effective_confidence is not None else view.confidence
    return GroundedBelief(
        category=str(getattr(view.category, "value", view.category)),
        subject_key=view.subject_key,
        statement=view.statement[:240],
        confidence=conf,
        evidence_count=view.evidence_count,
        status=status,
    )


async def resolve_evidence_grounding(
    session: AsyncSession, *, tenant: TenantContext, max_beliefs: int = _MAX_GROUNDING_BELIEFS
) -> tuple[str, EvidenceGrounding]:
    """Ground in the brand's evidence-graded beliefs. Brand-scoped (tenant
    isolation via the resolver). Never raises on an empty memory — it degrades to
    INSUFFICIENT_EVIDENCE. Includes contradicted beliefs so a generator can avoid
    acting on a conclusion newer outcomes have undermined."""
    resolution = await belief_resolver.resolve_beliefs(
        session, tenant=tenant, include_history=True, limit=max_beliefs
    )
    block = belief_resolver.to_context_block(resolution, max_beliefs=max_beliefs)

    grounded = [_to_grounded(b, status="active") for b in resolution.active[:max_beliefs]]
    contradicted = [_to_grounded(b, status="contradicted") for b in resolution.contradicted[:max_beliefs]]

    if contradicted:
        lines = ["", "=== CONTRADICTED (newer outcomes undermine these — do NOT rely on them) ==="]
        for b in contradicted:
            lines.append(f"- [{b.category}] {b.statement} (was {b.confidence}% confident)")
        block = block + "\n" + "\n".join(lines)

    if grounded:
        grounding = EvidenceGrounding(
            status="grounded",
            belief_count=len(grounded),
            beliefs=grounded,
            contradictions=contradicted,
            note=(
                "Grounded in the brand's evidence-graded beliefs formed from measured "
                "outcomes; confidence is server-derived, not asserted by the model."
            ),
        )
    else:
        grounding = EvidenceGrounding(
            status="insufficient_evidence",
            belief_count=0,
            beliefs=[],
            contradictions=contradicted,
            note=(
                "No validated beliefs from past results yet — any recommendation here is a "
                "hypothesis to validate, not an evidence-backed claim."
            ),
        )
    return block, grounding
