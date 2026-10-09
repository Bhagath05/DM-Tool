"""Phase 7.0 — explicit provenance tiers for the Business Context Resolver.

The resolver already composes business context from typed sources (profile,
Business Brain evidence kinds, ICP hypotheses, analytics, evaluated outcomes,
learning insights, the data-gap `unknown` list). Those typings are the source
of truth; this module does NOT duplicate or replace them. It provides ONE
cross-cutting vocabulary so BRO can tell the reader *where a piece of context
came from and how much to trust it*:

    USER_STATED     the business owner told us (profile, brand voice, goals)
    SYSTEM_INFERRED the system derived it, not confirmed (observations,
                    hypotheses, ICP hypotheses, the current strategy)
    VERIFIED        an evidence-backed, confirmed-style claim (BB facts, active)
    MEASURED        read from real first-party data (analytics KPIs, evaluated
                    outcomes)
    UNKNOWN         an explicit gap — we do NOT have this (the `unknown` list,
                    a missing profile, an absent strategy)

Mapping only — the classification below is the single place that maps existing
conventions to these tiers, so the agent prompt can carry an honest legend
without a new enum scattered across modules.
"""

from __future__ import annotations

from enum import StrEnum


class ContextProvenance(StrEnum):
    USER_STATED = "USER_STATED"
    SYSTEM_INFERRED = "SYSTEM_INFERRED"
    VERIFIED = "VERIFIED"
    MEASURED = "MEASURED"
    UNKNOWN = "UNKNOWN"


# Which resolver section carries which tier. Keyed by the section label the
# prompt block already uses, so the two stay in lock-step.
SECTION_PROVENANCE: dict[str, ContextProvenance] = {
    "Profile": ContextProvenance.USER_STATED,
    "Brand voice": ContextProvenance.USER_STATED,
    "Goals": ContextProvenance.USER_STATED,
    "FACTS": ContextProvenance.VERIFIED,
    "OBSERVATIONS": ContextProvenance.SYSTEM_INFERRED,
    "HYPOTHESES": ContextProvenance.SYSTEM_INFERRED,
    "ICP HYPOTHESES": ContextProvenance.SYSTEM_INFERRED,
    "STRATEGY": ContextProvenance.SYSTEM_INFERRED,
    "COMPETITOR CANDIDATES": ContextProvenance.SYSTEM_INFERRED,
    "MARKET SIGNALS": ContextProvenance.SYSTEM_INFERRED,
    "ANALYTICS": ContextProvenance.MEASURED,
    "OUTCOMES": ContextProvenance.MEASURED,
    "LEARNING INSIGHTS": ContextProvenance.SYSTEM_INFERRED,
    "Unknown": ContextProvenance.UNKNOWN,
}


def provenance_legend_block() -> str:
    """A compact legend for the LLM prompt so BRO treats each tier correctly:
    USER_STATED/SYSTEM_INFERRED are claims to verify, VERIFIED/MEASURED are
    grounded, UNKNOWN is a gap to acknowledge — never to fill with a guess."""
    return (
        "PROVENANCE TIERS (how much to trust each section):\n"
        "- USER_STATED: the owner told us (profile, brand voice, goals). "
        "Authoritative about intent; not independently verified.\n"
        "- SYSTEM_INFERRED: derived, not confirmed (observations, hypotheses, "
        "ICP, current strategy). Treat as a claim, never state as certain.\n"
        "- VERIFIED: evidence-backed confirmed-style claims (Business Brain facts).\n"
        "- MEASURED: real first-party data (analytics KPIs, evaluated outcomes). "
        "Do NOT fabricate these; if absent, say so.\n"
        "- UNKNOWN: an explicit gap. Acknowledge it and ask, never guess."
    )
