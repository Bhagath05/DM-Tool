"""Business Economics facet (Phase 7.20 Stage 2) — deterministic, migration-free.

Two layers, both pure (no DB, no LLM, no I/O):

1. **Calculators** — deterministic financial functions with EXPLICIT inputs and
   units. CAC / ROAS / CPA / conversion-rate are delegated to the existing
   ``trust.metrics`` registry (the canonical provider-verified money calculator);
   gross margin, LTV, LTV:CAC, break-even, and budget utilization are added here
   because ``trust.metrics`` does not define them. Every function returns a typed
   ``CalcResult`` that is NON-COMPUTABLE on a missing input, a zero/invalid
   denominator, or a non-finite result — never ``0`` / ``NaN`` / ``Inf``.

2. **Resolver** — ``resolve_economics`` assembles inputs from ALREADY-FETCHED
   existing sources (the onboarding profile row + the Marketing Brain analytics
   snapshot the DNA service already loaded) and produces provenance-tagged
   ``DnaItem`` rows + an overall status/note. It persists nothing and reads no new
   rows (so composition stays deterministic and write-free).

The LLM never computes or invents an authoritative financial number. Nothing is
fabricated: a value that cannot be derived from a real input is surfaced as
INSUFFICIENT_EVIDENCE with the inputs it still needs. No new storage is used;
persisting user-entered structured economics is deferred (needs a migration —
see the Stage 2 report).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aicmo.modules.business_dna.schemas import ContextProvenance, DnaItem

if TYPE_CHECKING:
    from aicmo.modules.business_dna.economics_schema import BusinessEconomics

__all__ = [
    "CalcResult",
    "break_even_customers",
    "break_even_revenue",
    "budget_utilization_pct",
    "cac_via_trust",
    "gross_margin_pct",
    "infer_currency",
    "ltv",
    "ltv_cac_ratio",
    "parse_amount_band",
    "resolve_economics",
]


# ---------------------------------------------------------------------
#  Typed result — mirrors the trust.metrics "never 0/NaN/Inf" contract.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class CalcResult:
    """A computed economics value, or an explicit non-computable result.

    ``computable=False`` carries a plain-language ``reason`` naming the missing or
    invalid input; ``value`` is then ``None`` (never a fabricated number)."""

    value: float | None
    unit: str
    computable: bool
    reason: str | None = None


def _insufficient(unit: str, reason: str) -> CalcResult:
    return CalcResult(value=None, unit=unit, computable=False, reason=reason)


def _finite(value: float, unit: str) -> CalcResult:
    if not math.isfinite(value):
        return _insufficient(unit, "Result is not a finite number.")
    return CalcResult(value=value, unit=unit, computable=True)


def _require(name: str, value: float | None, *, unit: str) -> float | CalcResult:
    """Return the float, or a non-computable CalcResult when missing/invalid."""
    if value is None:
        return _insufficient(unit, f"Missing required input: {name}.")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _insufficient(unit, f"Input {name!r} is not a number.")
    if not math.isfinite(v):
        return _insufficient(unit, f"Input {name!r} is not finite.")
    return v


# ---------------------------------------------------------------------
#  Calculators — explicit inputs + units. Rounding is applied here so the
#  surfaced value is already presentation-safe (currency 2dp, % 1dp, ratio 2dp).
# ---------------------------------------------------------------------


def gross_margin_pct(*, price: float | None, unit_cost: float | None) -> CalcResult:
    """Gross margin %. Inputs: price (currency/unit), unit_cost (currency/unit).
    Formula: (price - unit_cost) / price * 100. price<=0 → non-computable."""
    p = _require("price", price, unit="%")
    if isinstance(p, CalcResult):
        return p
    c = _require("unit_cost", unit_cost, unit="%")
    if isinstance(c, CalcResult):
        return c
    if p <= 0:
        return _insufficient("%", "Price must be greater than zero to compute margin.")
    return _finite(round((p - c) / p * 100.0, 1), "%")


def ltv(
    *,
    avg_order_value: float | None,
    purchases_per_year: float | None,
    lifespan_years: float | None,
    gross_margin_percent: float | None = 100.0,
) -> CalcResult:
    """Customer lifetime value (contribution). Inputs: avg_order_value (currency),
    purchases_per_year (count/yr), lifespan_years (yr), gross_margin_percent (%,
    default 100 = revenue LTV). Formula: AOV * purchases_per_year * lifespan_years
    * (margin/100)."""
    aov = _require("avg_order_value", avg_order_value, unit="currency")
    if isinstance(aov, CalcResult):
        return aov
    freq = _require("purchases_per_year", purchases_per_year, unit="currency")
    if isinstance(freq, CalcResult):
        return freq
    span = _require("lifespan_years", lifespan_years, unit="currency")
    if isinstance(span, CalcResult):
        return span
    margin = _require("gross_margin_percent", gross_margin_percent, unit="currency")
    if isinstance(margin, CalcResult):
        return margin
    if min(aov, freq, span) < 0 or not (0.0 <= margin <= 100.0):
        return _insufficient("currency", "LTV inputs must be non-negative and margin 0-100%.")
    return _finite(round(aov * freq * span * (margin / 100.0), 2), "currency")


def ltv_cac_ratio(*, ltv_value: float | None, cac_value: float | None) -> CalcResult:
    """LTV:CAC ratio (x). cac<=0 → non-computable (division guard)."""
    lv = _require("ltv", ltv_value, unit="x")
    if isinstance(lv, CalcResult):
        return lv
    cv = _require("cac", cac_value, unit="x")
    if isinstance(cv, CalcResult):
        return cv
    if cv <= 0:
        return _insufficient("x", "CAC must be greater than zero to compute LTV:CAC.")
    return _finite(round(lv / cv, 2), "x")


def break_even_revenue(*, fixed_costs: float | None, gross_margin_percent: float | None) -> CalcResult:
    """Revenue needed to cover fixed costs. Formula: fixed_costs / (margin/100).
    margin<=0 → non-computable."""
    fc = _require("fixed_costs", fixed_costs, unit="currency")
    if isinstance(fc, CalcResult):
        return fc
    gm = _require("gross_margin_percent", gross_margin_percent, unit="currency")
    if isinstance(gm, CalcResult):
        return gm
    if gm <= 0:
        return _insufficient("currency", "Gross margin must be greater than zero for break-even.")
    return _finite(round(fc / (gm / 100.0), 2), "currency")


def break_even_customers(*, fixed_costs: float | None, contribution_per_customer: float | None) -> CalcResult:
    """Customers needed to cover fixed costs. Formula: fixed_costs /
    contribution_per_customer. denominator<=0 → non-computable."""
    fc = _require("fixed_costs", fixed_costs, unit="customers")
    if isinstance(fc, CalcResult):
        return fc
    cpc = _require("contribution_per_customer", contribution_per_customer, unit="customers")
    if isinstance(cpc, CalcResult):
        return cpc
    if cpc <= 0:
        return _insufficient("customers", "Contribution per customer must be greater than zero.")
    return _finite(float(math.ceil(fc / cpc)), "customers")


def budget_utilization_pct(*, actual_spend: float | None, budget: float | None) -> CalcResult:
    """Share of marketing budget used. Formula: actual_spend / budget * 100.
    budget<=0 → non-computable."""
    spend = _require("actual_spend", actual_spend, unit="%")
    if isinstance(spend, CalcResult):
        return spend
    b = _require("budget", budget, unit="%")
    if isinstance(b, CalcResult):
        return b
    if b <= 0:
        return _insufficient("%", "Budget must be greater than zero to compute utilization.")
    return _finite(round(spend / b * 100.0, 1), "%")


def cac_via_trust(*, spend: float | None, new_customers: float | None, verified_source: bool) -> CalcResult:
    """CAC via the existing trust.metrics registry (the canonical money calculator).
    Monetary metrics require a provider-verified / first-party source, so
    ``verified_source`` must be True; otherwise the result is non-computable
    (unverified) exactly as trust enforces it."""
    from aicmo.modules.trust.enums import SourceTier

    tier = SourceTier.VERIFIED_PROVIDER if verified_source else SourceTier.USER_PROVIDED
    return _compute_trust_metric("cac", {"spend": spend, "new_customers": new_customers}, tier)


def _compute_trust_metric(name: str, inputs: dict, tier) -> CalcResult:
    from aicmo.modules.trust.contracts import ProposedMetric
    from aicmo.modules.trust.metrics import compute_metric

    clean = {k: v for k, v in inputs.items() if v is not None}
    mr = compute_metric(ProposedMetric(name=name, inputs=clean, source_tier=tier))
    if mr.computable and mr.value is not None:
        return _finite(round(float(mr.value), 2), mr.unit or "currency")
    reason = mr.reason_code.value if mr.reason_code is not None else "not_computable"
    return _insufficient(mr.unit or "currency", f"{name.upper()} not computable ({reason}).")


# ---------------------------------------------------------------------
#  Input parsing from existing fields (no new storage).
# ---------------------------------------------------------------------

# Country / region / US-state tokens → ISO 4217. Token-matched (never substring),
# so "Austin" never matches "us". Absent/unknown → None (currency UNKNOWN, never
# a silent USD default).
_CURRENCY_TOKENS: dict[str, str] = {
    "india": "INR", "in": "INR", "bharat": "INR",
    "usa": "USD", "us": "USD", "u.s": "USD", "u.s.a": "USD", "america": "USD", "united": "USD",
    "uk": "GBP", "u.k": "GBP", "britain": "GBP", "england": "GBP", "scotland": "GBP", "wales": "GBP",
    "uae": "AED", "emirates": "AED", "dubai": "AED", "abu": "AED",
    "canada": "CAD", "australia": "AUD", "singapore": "SGD", "japan": "JPY",
    "germany": "EUR", "france": "EUR", "spain": "EUR", "italy": "EUR", "ireland": "EUR",
    "netherlands": "EUR", "portugal": "EUR", "eurozone": "EUR",
}
# US state abbreviations → USD (e.g. "Austin, TX").
_US_STATES: frozenset[str] = frozenset(
    "al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo "
    "mt ne nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy".split()
)
# "in" is both India and Indiana's abbreviation — treat the US-state meaning only
# when another US token is present; a bare "in" token maps to INR below.


def infer_currency(location: str | None) -> tuple[str | None, str | None]:
    """Infer an ISO-4217 currency from a free-text location by WHOLE-TOKEN match.
    Returns ``(code, reason)`` or ``(None, None)`` when nothing matches (UNKNOWN —
    never guessed). SYSTEM_INFERRED when it resolves."""
    if not location or not str(location).strip():
        return None, None
    tokens = [t for t in re.split(r"[^a-z]+", str(location).lower()) if t]
    token_set = set(tokens)
    for t in tokens:
        if t in _CURRENCY_TOKENS:
            return _CURRENCY_TOKENS[t], f"inferred from location token '{t}'"
    # US state abbreviation (skip bare 'in', handled as India above).
    for t in tokens:
        if t != "in" and t in _US_STATES:
            return "USD", f"inferred from US state token '{t.upper()}'"
    if "in" in token_set:
        return "INR", "inferred from location token 'in'"
    return None, None


_AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def parse_amount_band(band: str | None) -> tuple[float | None, float | None]:
    """Parse a stated range like '$100-500' or '0-10' into ``(low, high)`` floats,
    or ``(None, None)`` when unparseable. A single number → ``(n, n)``. Derived
    from a user-stated band, so the caller tags it SYSTEM_INFERRED (a band, not a
    precise figure)."""
    if not band or not str(band).strip():
        return None, None
    nums = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(str(band))]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums[0], nums[1]), max(nums[0], nums[1])


# ---------------------------------------------------------------------
#  Facet resolver — maps existing inputs + calculators → provenance items.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class EconomicsResolution:
    items: list[DnaItem]
    status: str  # "populated" | "insufficient_evidence" | "unknown"
    note: str
    currency: str | None
    period: str | None
    # Trust tier of ``period`` (USER_STATED when owner-stated, MEASURED when from
    # measured analytics); None when there is no period. Never fabricated.
    period_provenance: ContextProvenance | None = None


def resolve_economics(
    *, profile_row, analytics, economics: BusinessEconomics | None = None, now_label: str = "current"
) -> EconomicsResolution:
    """Assemble the economics facet from ALREADY-FETCHED sources (no new reads).

    ``profile_row``: the onboarding BusinessProfile row (or None).
    ``analytics``: the Marketing Brain analytics snapshot (or None).
    ``economics``: the brand's persisted structured economics inputs (or None).

    When economics inputs are present the deterministic calculators compute the
    real metrics; otherwise every metric is honest INSUFFICIENT_EVIDENCE. The LLM
    never computes a figure and nothing is fabricated.
    """
    items: list[DnaItem] = []
    location = getattr(profile_row, "business_location", None) if profile_row is not None else None

    # Reporting currency: a stored (USER_STATED) currency wins over one inferred
    # from the location (SYSTEM_INFERRED); absent both → UNKNOWN (never guessed).
    currency: str | None = None
    if economics is not None and economics.currency:
        currency = economics.currency
        items.append(
            DnaItem(
                label="Reporting currency", detail=currency,
                provenance=ContextProvenance.USER_STATED, source="economics.currency",
            )
        )
    else:
        currency, cur_reason = infer_currency(location)
        if currency is not None:
            items.append(
                DnaItem(
                    label="Reporting currency", detail=currency,
                    provenance=ContextProvenance.SYSTEM_INFERRED,
                    source=f"profile.location ({cur_reason})",
                )
            )
    # Reporting period: owner-stated (USER_STATED) when supplied; otherwise filled
    # from measured analytics below (MEASURED). Never inferred from a value.
    period = economics.reporting_period if (economics is not None and economics.reporting_period) else None
    period_provenance: ContextProvenance | None = (
        ContextProvenance.USER_STATED if period is not None else None
    )

    # --- USER_STATED context from existing profile fields ---
    if profile_row is not None:
        band = getattr(profile_row, "monthly_budget_band", None)
        if band:
            items.append(
                DnaItem(
                    label="Marketing budget (monthly, stated band)",
                    detail=str(band),
                    provenance=ContextProvenance.USER_STATED,
                    source="profile.monthly_budget_band",
                )
            )
        pricing = getattr(profile_row, "pricing", None)
        if pricing and str(pricing).strip():
            items.append(
                DnaItem(
                    label="Pricing (owner-stated)",
                    detail=str(pricing)[:400],
                    provenance=ContextProvenance.USER_STATED,
                    source="profile.pricing",
                )
            )
        goal = getattr(profile_row, "primary_goal_text", None)
        if goal and str(goal).strip():
            items.append(
                DnaItem(
                    label="Revenue/growth target (stated, unstructured)",
                    detail=str(goal)[:300],
                    provenance=ContextProvenance.USER_STATED,
                    source="profile.primary_goal_text",
                )
            )
        for label, attr in (("Products (revenue streams)", "products"), ("Services (revenue streams)", "services")):
            vals = [str(v).strip() for v in (getattr(profile_row, attr, None) or []) if str(v).strip()]
            if vals:
                items.append(
                    DnaItem(
                        label=label,
                        detail=", ".join(vals[:20]),
                        provenance=ContextProvenance.USER_STATED,
                        source=f"profile.{attr}",
                    )
                )

    # --- Stored structured economics inputs (each keeps its OWN provenance) ---
    if economics is not None:
        if economics.revenue_model:
            items.append(
                DnaItem(label="Revenue model", detail=economics.revenue_model,
                        provenance=ContextProvenance.USER_STATED, source="economics")
            )
        if economics.revenue_streams:
            items.append(
                DnaItem(label="Revenue streams", detail=", ".join(economics.revenue_streams[:20]),
                        provenance=ContextProvenance.USER_STATED, source="economics")
            )
        for label, fname in (
            ("Unit price", "price"), ("Unit cost (COGS)", "unit_cost"),
            ("Fixed costs (per period)", "fixed_costs"), ("Average order value", "avg_order_value"),
            ("Purchases per year", "purchases_per_year"), ("Customer lifespan (years)", "lifespan_years"),
            ("Marketing budget (monthly)", "marketing_budget_monthly"), ("Revenue target", "target_revenue"),
        ):
            ev = getattr(economics, fname)
            if ev is not None:
                items.append(
                    DnaItem(
                        label=label, detail=_fmt_money(ev.value, ev.currency or currency),
                        provenance=ev.provenance, source=ev.source or "economics",
                        status=ev.reporting_period,
                    )
                )

    # --- MEASURED conversion economics from analytics (if present) ---
    if analytics is not None:
        if period is None:
            period = "last 30 days"
            period_provenance = ContextProvenance.MEASURED
        items.append(
            DnaItem(
                label="Conversion rate (landing pages)",
                detail=f"{analytics.conversion_rate:.1%}",
                provenance=ContextProvenance.MEASURED,
                source="analytics",
                status="last 30 days",
            )
        )
        items.append(
            DnaItem(
                label="Leads (30d) / submissions",
                detail=f"{analytics.leads_30d} leads · {analytics.total_submissions} submissions",
                provenance=ContextProvenance.MEASURED,
                source="analytics",
                status="last 30 days",
            )
        )

    # --- Deterministic computed metrics (from stored inputs when present) ------
    gm = gross_margin_pct(price=_val(economics, "price"), unit_cost=_val(economics, "unit_cost"))
    items.append(_metric_item("Gross margin", gm, currency, needs="unit price and unit cost (COGS)"))
    gm_value = gm.value if gm.computable else None

    ltv_res = ltv(
        avg_order_value=_val(economics, "avg_order_value"),
        purchases_per_year=_val(economics, "purchases_per_year"),
        lifespan_years=_val(economics, "lifespan_years"),
        gross_margin_percent=gm_value if gm_value is not None else 100.0,
    )
    items.append(
        _metric_item("Customer lifetime value (LTV)", ltv_res, currency,
                     needs="average order value, purchases per year, and customer lifespan")
    )

    # CAC requires a provider-verified spend source (credential-gated) — honest gap.
    cac = cac_via_trust(spend=None, new_customers=None, verified_source=False)
    items.append(
        _metric_item("Customer acquisition cost (CAC)", cac, currency,
                     needs="a provider-verified ad spend and new-customer count (connect an ad account)")
    )

    lc = ltv_cac_ratio(
        ltv_value=ltv_res.value if ltv_res.computable else None,
        cac_value=cac.value if cac.computable else None,
    )
    items.append(_metric_item("LTV:CAC ratio", lc, currency, needs="a computable LTV and a provider-verified CAC"))

    ber = break_even_revenue(fixed_costs=_val(economics, "fixed_costs"), gross_margin_percent=gm_value)
    items.append(_metric_item("Break-even revenue", ber, currency, needs="fixed costs and gross margin"))

    price_v, cost_v = _val(economics, "price"), _val(economics, "unit_cost")
    contribution = (price_v - cost_v) if (price_v is not None and cost_v is not None) else None
    bec = break_even_customers(fixed_costs=_val(economics, "fixed_costs"), contribution_per_customer=contribution)
    items.append(
        _metric_item("Break-even customers", bec, currency,
                     needs="fixed costs and contribution per customer (unit price less unit cost)")
    )

    # Budget utilization still needs a provider-verified spend to compare against.
    items.append(
        _needs("Budget utilization",
               "a provider-verified monthly ad spend to compare against the budget")
    )

    # Status: populated when any grounded value (owner-stated / verified / measured)
    # is present — including stored economics inputs. Computed SYSTEM_INFERRED
    # metrics do not by themselves make the facet "populated".
    grounded = [
        i for i in items
        if i.provenance in (ContextProvenance.USER_STATED, ContextProvenance.VERIFIED, ContextProvenance.MEASURED)
    ]
    if grounded:
        status = "populated"
    elif economics is not None or profile_row is not None or analytics is not None:
        status = "insufficient_evidence"
    else:
        status = "unknown"

    note = (
        "Owner-stated and stored economics inputs are shown with their own "
        "provenance, currency and period. Deterministic metrics (gross margin, LTV, "
        "break-even) are computed when their inputs exist and are INSUFFICIENT_EVIDENCE "
        "otherwise; CAC and budget utilization require a provider-verified spend "
        "source. No value is fabricated and the model never computes a figure."
    )
    return EconomicsResolution(
        items=items, status=status, note=note, currency=currency,
        period=period, period_provenance=period_provenance,
    )


def _val(economics: BusinessEconomics | None, fname: str) -> float | None:
    if economics is None:
        return None
    ev = getattr(economics, fname, None)
    return ev.value if ev is not None else None


def _fmt_money(value: float, currency: str | None) -> str:
    base = f"{value:,.2f}"
    return f"{base} {currency}" if currency else base


def _fmt_calc(r: CalcResult, currency: str | None) -> str:
    if r.value is None:
        return "n/a"
    if r.unit == "%":
        return f"{r.value}%"
    if r.unit == "x":
        return f"{r.value}x"
    if r.unit == "customers":
        return f"{int(r.value)} customers"
    return _fmt_money(r.value, currency)


def _metric_item(label: str, r: CalcResult, currency: str | None, *, needs: str) -> DnaItem:
    """A computed metric → SYSTEM_INFERRED item (derived from stored inputs), or an
    honest INSUFFICIENT_EVIDENCE item naming the inputs it still needs."""
    if r.computable and r.value is not None:
        return DnaItem(
            label=label, detail=_fmt_calc(r, currency),
            provenance=ContextProvenance.SYSTEM_INFERRED,
            source="derived from stored economics inputs (deterministic)",
        )
    return _needs(label, needs)


def _needs(label: str, needs: str) -> DnaItem:
    return DnaItem(
        label=label,
        detail=f"INSUFFICIENT_EVIDENCE — provide {needs}.",
        provenance=ContextProvenance.UNKNOWN,
        status="insufficient_evidence",
    )
