"""Deterministic metric registry (Trust Layer T0).

The LLM never computes a user-visible number. Every metric DM Tool will show is
computed here, in code, from named raw inputs. The contract:

* A missing input, a zero/invalid denominator, or a non-finite result yields a
  terminal ``NOT_COMPUTABLE`` result — **never** ``0``, ``NaN``, or ``Inf``.
* Monetary metrics (spend, revenue, ROAS, CAC, CPA) require a provider-verified
  or first-party source; otherwise they are ``NOT_COMPUTABLE`` (unverified).
* An unknown metric name is ``MISSING_METRIC`` — the registry never guesses.

Nothing here reads a database or a provider; callers pass already-fetched raw
inputs. This keeps the registry pure and unit-testable.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from aicmo.modules.trust.contracts import MetricResult, ProposedMetric
from aicmo.modules.trust.enums import ReasonCode, SourceTier

_VERIFIED_SOURCES: frozenset[SourceTier] = frozenset(
    {SourceTier.VERIFIED_PROVIDER, SourceTier.FIRST_PARTY_DATA}
)


class _NotComputableError(Exception):
    """Raised inside a compute fn to signal a terminal non-computable result."""

    def __init__(self, reason: ReasonCode) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _num(inputs: dict, key: str) -> float:
    if key not in inputs or inputs[key] is None:
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE)
    try:
        v = float(inputs[key])
    except (TypeError, ValueError) as exc:
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE) from exc
    if not math.isfinite(v):
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE)
    return v


def _nonneg(inputs: dict, key: str) -> float:
    v = _num(inputs, key)
    if v < 0:
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE)
    return v


def _ratio(numerator: float, denominator: float, *, scale: float = 1.0) -> float:
    if denominator == 0:
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE)
    result = (numerator / denominator) * scale
    if not math.isfinite(result):
        raise _NotComputableError(ReasonCode.NOT_COMPUTABLE)
    return result


@dataclass(frozen=True)
class _MetricDef:
    unit: str
    monetary: bool
    compute: Callable[[dict], float]


_REGISTRY: dict[str, _MetricDef] = {
    # raw counts (passthrough, validated non-negative)
    "impressions": _MetricDef("", False, lambda i: _nonneg(i, "impressions")),
    "clicks": _MetricDef("", False, lambda i: _nonneg(i, "clicks")),
    "conversions": _MetricDef("", False, lambda i: _nonneg(i, "conversions")),
    # monetary raw
    "spend": _MetricDef("currency", True, lambda i: _nonneg(i, "spend")),
    "revenue": _MetricDef("currency", True, lambda i: _nonneg(i, "revenue")),
    # derived rates
    "ctr": _MetricDef("%", False, lambda i: _ratio(_nonneg(i, "clicks"), _nonneg(i, "impressions"), scale=100.0)),
    "conversion_rate": _MetricDef("%", False, lambda i: _ratio(_nonneg(i, "conversions"), _nonneg(i, "clicks"), scale=100.0)),
    # monetary derived
    "roas": _MetricDef("x", True, lambda i: _ratio(_nonneg(i, "revenue"), _nonneg(i, "spend"))),
    "cac": _MetricDef("currency", True, lambda i: _ratio(_nonneg(i, "spend"), _nonneg(i, "new_customers"))),
    "cpa": _MetricDef("currency", True, lambda i: _ratio(_nonneg(i, "spend"), _nonneg(i, "conversions"))),
    # change (baseline may be negative; denominator uses magnitude)
    "percentage_change": _MetricDef("%", False, lambda i: _ratio(_num(i, "current") - _num(i, "baseline"), abs(_num(i, "baseline")), scale=100.0)),
}


def is_known_metric(name: str) -> bool:
    return name.strip().lower() in _REGISTRY


def compute_metric(proposed: ProposedMetric) -> MetricResult:
    """Compute one metric deterministically. Never raises for bad data — returns
    a ``NOT_COMPUTABLE`` / ``MISSING_METRIC`` result instead."""
    name = proposed.name.strip().lower()
    definition = _REGISTRY.get(name)
    if definition is None:
        return MetricResult(
            name=proposed.name, value=None, computable=False,
            reason_code=ReasonCode.MISSING_METRIC, source_tier=proposed.source_tier,
        )

    # Monetary metrics must trace to a verified/first-party source.
    if definition.monetary and proposed.source_tier not in _VERIFIED_SOURCES:
        return MetricResult(
            name=name, value=None, unit=definition.unit, computable=False,
            reason_code=ReasonCode.UNVERIFIED_SOURCE, source_tier=proposed.source_tier,
        )

    try:
        value = definition.compute(proposed.inputs)
    except _NotComputableError as exc:
        return MetricResult(
            name=name, value=None, unit=definition.unit, computable=False,
            reason_code=exc.reason, source_tier=proposed.source_tier,
        )

    # Defence in depth: never surface a non-finite number.
    if not math.isfinite(value):
        return MetricResult(
            name=name, value=None, unit=definition.unit, computable=False,
            reason_code=ReasonCode.NOT_COMPUTABLE, source_tier=proposed.source_tier,
        )

    return MetricResult(
        name=name, value=value, unit=definition.unit, computable=True,
        reason_code=None, source_tier=proposed.source_tier,
    )
