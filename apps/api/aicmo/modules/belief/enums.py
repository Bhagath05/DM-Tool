"""Controlled vocabularies for the belief/learning memory layer."""

from __future__ import annotations

import enum


class BeliefCategory(enum.StrEnum):
    BUSINESS = "business"
    AUDIENCE = "audience"
    MARKET = "market"
    POSITIONING = "positioning"
    OFFER = "offer"
    CONTENT = "content"
    CHANNEL = "channel"
    CAMPAIGN = "campaign"
    CREATIVE = "creative"
    PERFORMANCE = "performance"
    LEARNING = "learning"


class BeliefStatus(enum.StrEnum):
    ACTIVE = "active"  # currently held, evidence-supported
    SUPERSEDED = "superseded"  # replaced by a newer belief (chain retained)
    CONTRADICTED = "contradicted"  # contradicting evidence outweighs support
    UNVALIDATED = "unvalidated"  # no supporting evidence yet — not fact
    RETIRED = "retired"  # deliberately closed out


class EvidenceRefKind(enum.StrEnum):
    """What a belief-evidence reference points at. DB-backed kinds are validated
    for tenant ownership; DATA_SOURCE is a provenance label only."""

    BRAIN_EVIDENCE = "brain_evidence"
    ADVISOR_RECOMMENDATION = "advisor_recommendation"
    ADVISOR_OUTCOME = "advisor_outcome"
    LEARNING_INSIGHT = "learning_insight"
    DATA_SOURCE = "data_source"


class EvidenceRelation(enum.StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


# ref_kind → (table, brand column). Hardcoded allowlist — never built from input,
# so it cannot be used for SQL injection. Used to validate tenant ownership of a
# referenced row. DATA_SOURCE is intentionally absent (no DB row).
DB_BACKED_REFS: dict[str, str] = {
    EvidenceRefKind.BRAIN_EVIDENCE.value: "brain_evidence",
    EvidenceRefKind.ADVISOR_RECOMMENDATION.value: "advisor_recommendations",
    EvidenceRefKind.ADVISOR_OUTCOME.value: "advisor_outcomes",
    EvidenceRefKind.LEARNING_INSIGHT.value: "learning_insights",
}

# Kinds whose supporting evidence counts as EXPERIMENTAL (measured outcomes),
# which raises the confidence ceiling vs. observational evidence.
EXPERIMENTAL_REF_KINDS: frozenset[str] = frozenset(
    {EvidenceRefKind.ADVISOR_OUTCOME.value}
)
