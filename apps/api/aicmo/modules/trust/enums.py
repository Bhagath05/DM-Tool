"""Controlled vocabularies for the Trust Layer (T0).

All StrEnum so they serialize as their lowercase/uppercase string values and
coerce cleanly in Pydantic. These mirror the approved architecture contract;
no new semantic states are introduced here.
"""

from __future__ import annotations

import enum


class ClaimType(enum.StrEnum):
    """The trust ladder (monotonic). The Trust Layer may only *demote* a type."""

    FACT = "fact"
    OBSERVATION = "observation"
    INTERPRETATION = "interpretation"
    HYPOTHESIS = "hypothesis"
    RECOMMENDATION = "recommendation"


class EvidenceBand(enum.StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class CausalLevel(enum.StrEnum):
    """Causal evidence hierarchy (weakest → strongest). Today DM Tool reaches at
    most QUASI_EXPERIMENTAL; the top two are reserved for real experiments."""

    OBSERVATIONAL = "observational"
    ASSOCIATIONAL = "associational"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    CONTROLLED_EXPERIMENT = "controlled_experiment"
    RANDOMIZED = "randomized"


class SourceTier(enum.StrEnum):
    """Provenance quality for a given claim — NOT a universal ranking."""

    VERIFIED_PROVIDER = "verified_provider"
    FIRST_PARTY_DATA = "first_party_data"
    USER_PROVIDED = "user_provided"
    DERIVED_INTERNAL = "derived_internal"
    RESEARCH = "research"
    MODEL_INFERENCE = "model_inference"
    UNKNOWN = "unknown"


class ConsequenceLevel(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClaimStatus(enum.StrEnum):
    ACTIVE = "active"
    MIXED = "mixed"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class RecommendationStatus(enum.StrEnum):
    SUPPORTED = "supported"
    QUALIFIED = "qualified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTRADICTED = "contradicted"
    HIGH_RISK_REQUIRES_REVIEW = "high_risk_requires_review"


class EvidenceStatus(enum.StrEnum):
    OK = "ok"
    MIXED_EVIDENCE = "mixed_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class TrustVerdict(enum.StrEnum):
    """Overall disposition for a validated response (the only states defined by
    the architecture; adding one requires documenting why)."""

    ACCEPT = "accept"
    DOWNGRADE = "downgrade"
    QUALIFY = "qualify"
    REJECT = "reject"
    MIXED = "mixed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ReasonCode(enum.StrEnum):
    """Machine-readable reasons for a downgrade / rejection / insufficiency."""

    # fabrication / resolvability
    FABRICATED_METRIC = "fabricated_metric"
    UNRESOLVABLE_EVIDENCE = "unresolvable_evidence"
    MISSING_METRIC = "missing_metric"
    NOT_COMPUTABLE = "not_computable"
    UNVERIFIED_SOURCE = "unverified_source"
    # causality
    UNSUPPORTED_CAUSAL_CLAIM = "unsupported_causal_claim"
    CAUSAL_SCOPE_EXCEEDED = "causal_scope_exceeded"
    # confidence
    CONFIDENCE_OVER_CEILING = "confidence_over_ceiling"
    # evidence sufficiency / comparability / freshness
    SMALL_SAMPLE = "small_sample"
    INCOMPLETE_ATTRIBUTION = "incomplete_attribution"
    STALE_DATA = "stale_data"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INCOMPARABLE_COHORTS = "incomparable_cohorts"
    # recommendation
    RECOMMENDATION_EXCEEDS_EVIDENCE = "recommendation_exceeds_evidence"
    HIGH_CONSEQUENCE_UNDER_EVIDENCED = "high_consequence_under_evidenced"
