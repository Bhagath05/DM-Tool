"""Business DNA — Phase 7.20 Stage 1.

ONE canonical, read-only, provenance-aware projection of everything DM Tool
already knows about a brand, assembled from the EXISTING intelligence stores and
composition services. It creates no new store, no table, and no migration; it
reuses Marketing Brain composition, the shared belief-grounding foundation, the
onboarding profile, and the social audience patterns, and re-projects them into
provenance-tagged facets.

Deterministic: no LLM call participates in composition. Confidence and freshness
are server-derived (never model-asserted); missing data is surfaced as explicit
UNKNOWN / INSUFFICIENT_EVIDENCE rather than fabricated.
"""

from aicmo.modules.business_dna.schemas import (
    BusinessDna,
    DnaFacet,
    DnaItem,
    FacetStatus,
)
from aicmo.modules.business_dna.service import get_business_dna

__all__ = [
    "BusinessDna",
    "DnaFacet",
    "DnaItem",
    "FacetStatus",
    "get_business_dna",
]
