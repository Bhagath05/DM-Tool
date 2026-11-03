"""Typed Business DNA read model (Phase 7.20 Stage 1).

The public provenance vocabulary is the single standard adopted in Stage 0
(`docs/product/PROVENANCE_STANDARD.md`): it REUSES
``marketing_brain.provenance.ContextProvenance`` rather than defining a parallel
enum, so there is exactly one public tier set across the platform.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# Reuse the Stage-0 canonical public provenance vocabulary — do not redefine it.
from aicmo.modules.marketing_brain.provenance import ContextProvenance

__all__ = [
    "BusinessDna",
    "ContextProvenance",
    "DnaFacet",
    "DnaItem",
    "FacetStatus",
]


class FacetStatus(StrEnum):
    """Whether a facet carries grounded content, or is honestly empty.

    POPULATED: at least one real item.
    INSUFFICIENT_EVIDENCE: the source exists for this brand but holds nothing yet.
    UNKNOWN: the source itself is absent (e.g. no profile, or a deferred facet).
    """

    POPULATED = "populated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"


class DnaItem(BaseModel):
    """One provenance-tagged fact/claim/number inside a facet.

    ``confidence`` is populated ONLY when server-derived (belief memory) or
    measured; it is never an LLM-asserted number. ``freshness`` carries the
    plain-language decay reason when the source supports read-time freshness
    (beliefs today). ``status`` preserves the underlying row status (e.g. a
    belief/evidence/ICP/recommendation status) so a consumer can reason about it.
    """

    label: str
    detail: str | None = None
    provenance: ContextProvenance
    confidence: int | None = Field(default=None, ge=0, le=100)
    freshness: str | None = None
    source: str | None = None
    status: str | None = None


class DnaFacet(BaseModel):
    """One dimension of the business (identity, audience, market, …)."""

    key: str
    title: str
    status: FacetStatus
    provenance_tiers: list[ContextProvenance] = Field(default_factory=list)
    items: list[DnaItem] = Field(default_factory=list)
    # Beliefs/evidence that newer outcomes have undermined — surfaced, never
    # silently dropped (reuses the existing belief contradiction mechanism).
    contradictions: list[DnaItem] = Field(default_factory=list)
    note: str | None = None


class BusinessDna(BaseModel):
    """The canonical, read-only Business DNA snapshot for one brand.

    Composition is deterministic and independent of LLM output. ``generated_at``
    is the only field expected to vary between two otherwise-identical runs.
    """

    brand_id: uuid.UUID
    organization_id: uuid.UUID
    generated_at: datetime

    facets: list[DnaFacet] = Field(default_factory=list)
    known: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    provenance_legend: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    def facet(self, key: str) -> DnaFacet | None:
        """Convenience lookup by facet key (consumers project what they need)."""
        for f in self.facets:
            if f.key == key:
                return f
        return None
