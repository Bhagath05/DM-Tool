"""Source taxonomy predicates (Trust Layer T0).

``SourceTier`` describes the *provenance* of a piece of evidence — where it came
from — and is deliberately **not** a single universal ranking (user-provided
data is not globally "better" or "worse" than research; it depends on the
claim). What the taxonomy does encode is a small set of hard gates:

* ``MODEL_INFERENCE`` and ``UNKNOWN`` can never, on their own, back a FACT, a
  user-visible metric, or a causal claim — those require real observed data.
* Monetary facts/metrics additionally require a provider-verified or first-party
  source (enforced in :mod:`aicmo.modules.trust.metrics`).

These are pure predicates over the enum; no I/O, no ranking arithmetic.
"""

from __future__ import annotations

from collections.abc import Iterable

from aicmo.modules.trust.enums import SourceTier

# Tiers that are NOT real observed data — they may illustrate or hypothesize,
# but may not stand as the sole basis for a fact, metric, or causal claim.
_NON_GROUNDING: frozenset[SourceTier] = frozenset(
    {SourceTier.MODEL_INFERENCE, SourceTier.UNKNOWN}
)

# Observed-data tiers strong enough to back a monetary fact/metric.
_MONETARY_GRADE: frozenset[SourceTier] = frozenset(
    {SourceTier.VERIFIED_PROVIDER, SourceTier.FIRST_PARTY_DATA}
)


def is_grounding(tier: SourceTier) -> bool:
    """True if the tier is real observed data (not model inference / unknown)."""
    return tier not in _NON_GROUNDING


def can_back_fact(tiers: Iterable[SourceTier]) -> bool:
    """A FACT needs at least one grounding source."""
    return any(is_grounding(t) for t in tiers)


def can_back_metric(tier: SourceTier) -> bool:
    """A user-visible metric needs a grounding source (monetary gating is
    additionally applied in the metric registry)."""
    return is_grounding(tier)


def can_back_causal(tiers: Iterable[SourceTier]) -> bool:
    """A causal claim needs at least one grounding source."""
    return any(is_grounding(t) for t in tiers)


def is_monetary_grade(tier: SourceTier) -> bool:
    return tier in _MONETARY_GRADE
