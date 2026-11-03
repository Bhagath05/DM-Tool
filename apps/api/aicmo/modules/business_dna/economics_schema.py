"""Validated Business Economics payload (Phase 7.20 Stage 2b).

The Pydantic contract for the ``business_profiles.economics`` JSONB column. Every
financial input is an ``EconomicValue`` carrying its own provenance, source,
currency, reporting period and timestamp — so a stored number is never a bare
figure. ``extra="forbid"`` rejects unknown keys, and UNKNOWN provenance is not a
writable tier (there is nothing to store for an unknown).

This schema is validation-only; it never computes a metric (the calculators in
``economics.py`` do that) and never performs I/O (``economics_store.py`` does).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aicmo.modules.business_dna.schemas import ContextProvenance

__all__ = ["BusinessEconomics", "EconomicValue"]

# A stored value must carry a trust-bearing provenance. UNKNOWN is excluded: an
# unknown has nothing to persist, and SYSTEM_INFERRED (model-derived) is allowed
# but can never overwrite a USER_STATED / VERIFIED value (enforced in the store).
_WRITABLE_PROVENANCE: frozenset[ContextProvenance] = frozenset(
    {
        ContextProvenance.USER_STATED,
        ContextProvenance.SYSTEM_INFERRED,
        ContextProvenance.VERIFIED,
        ContextProvenance.MEASURED,
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EconomicValue(BaseModel):
    """One financial input with full provenance."""

    model_config = ConfigDict(extra="forbid")

    value: float = Field(ge=0)
    provenance: ContextProvenance
    source: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    reporting_period: str | None = Field(default=None, max_length=64)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("economic value must be a finite, non-negative number")
        return v

    @field_validator("provenance")
    @classmethod
    def _writable(cls, v: ContextProvenance) -> ContextProvenance:
        if v not in _WRITABLE_PROVENANCE:
            raise ValueError(
                f"provenance {v!r} is not writable for a stored economics value "
                f"(allowed: USER_STATED, SYSTEM_INFERRED, VERIFIED, MEASURED)"
            )
        return v

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    def is_protected(self) -> bool:
        """USER_STATED / VERIFIED values may not be overwritten by a model-derived
        (SYSTEM_INFERRED) value — the Stage 2b no-LLM-overwrite guarantee."""
        return self.provenance in (ContextProvenance.USER_STATED, ContextProvenance.VERIFIED)


class BusinessEconomics(BaseModel):
    """The structured economics inputs stored for one brand. All fields optional
    so a brand can fill them incrementally; an absent field is honest absence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    # Reporting context (currency is ISO-4217; period e.g. "monthly", "FY2026").
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    reporting_period: str | None = Field(default=None, max_length=64)
    # Descriptive revenue context (USER_STATED by nature).
    revenue_model: str | None = Field(default=None, max_length=200)
    revenue_streams: list[str] = Field(default_factory=list, max_length=30)

    # Numeric inputs the deterministic calculators consume. Each is provenance-
    # tagged; the calculators derive margin / LTV / break-even from them.
    price: EconomicValue | None = None  # unit / avg selling price
    unit_cost: EconomicValue | None = None  # COGS per unit
    fixed_costs: EconomicValue | None = None  # per reporting period
    avg_order_value: EconomicValue | None = None
    purchases_per_year: EconomicValue | None = None
    lifespan_years: EconomicValue | None = None
    marketing_budget_monthly: EconomicValue | None = None
    target_revenue: EconomicValue | None = None

    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    # The provenance-tagged numeric fields, in a stable order (used by the store's
    # merge and by the resolver). Keep in sync with the fields above.
    VALUE_FIELDS: ClassVar[tuple[str, ...]] = (
        "price",
        "unit_cost",
        "fixed_costs",
        "avg_order_value",
        "purchases_per_year",
        "lifespan_years",
        "marketing_budget_monthly",
        "target_revenue",
    )
