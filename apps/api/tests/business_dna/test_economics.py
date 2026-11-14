"""Phase 7.20 Stage 2 — Business Economics calculators + resolver (pure, no DB).

Covers valid/invalid inputs, missing values, zero denominators, currency
inference (and honest UNKNOWN, never a guess), band parsing, precision/rounding,
provenance, explicit reporting period, and the resolver's INSUFFICIENT_EVIDENCE
behaviour. Nothing here touches a DB or an LLM.
"""

from __future__ import annotations

from types import SimpleNamespace

from aicmo.modules.business_dna import economics as ec
from aicmo.modules.business_dna.schemas import ContextProvenance
from aicmo.modules.marketing_brain.schemas import MarketingBrainAnalyticsSnapshot

# ---------------------------------------------------------------------
#  Calculators — valid, missing, zero-denominator, rounding
# ---------------------------------------------------------------------


def test_gross_margin_valid_and_rounded():
    r = ec.gross_margin_pct(price=100.0, unit_cost=40.0)
    assert r.computable and r.value == 60.0 and r.unit == "%"
    # Rounding to 1dp.
    r2 = ec.gross_margin_pct(price=99.99, unit_cost=33.33)
    assert r2.computable and r2.value == round((99.99 - 33.33) / 99.99 * 100, 1)


def test_gross_margin_missing_and_zero_price():
    assert ec.gross_margin_pct(price=None, unit_cost=40.0).computable is False
    assert ec.gross_margin_pct(price=100.0, unit_cost=None).computable is False
    zero = ec.gross_margin_pct(price=0.0, unit_cost=10.0)
    assert zero.computable is False and zero.value is None  # never 0/Inf


def test_ltv_valid_and_margin_bounds():
    r = ec.ltv(avg_order_value=100.0, purchases_per_year=4.0, lifespan_years=3.0, gross_margin_percent=50.0)
    assert r.computable and r.value == 600.0  # 100*4*3*0.5
    assert ec.ltv(avg_order_value=100.0, purchases_per_year=4.0, lifespan_years=3.0, gross_margin_percent=150.0).computable is False
    assert ec.ltv(avg_order_value=None, purchases_per_year=4.0, lifespan_years=3.0).computable is False


def test_ltv_cac_ratio_zero_denominator():
    assert ec.ltv_cac_ratio(ltv_value=600.0, cac_value=150.0).value == 4.0
    z = ec.ltv_cac_ratio(ltv_value=600.0, cac_value=0.0)
    assert z.computable is False and z.value is None


def test_break_even_revenue_and_customers():
    assert ec.break_even_revenue(fixed_costs=5000.0, gross_margin_percent=50.0).value == 10000.0
    assert ec.break_even_revenue(fixed_costs=5000.0, gross_margin_percent=0.0).computable is False
    # Customers rounds UP (you can't break even on a fractional customer).
    r = ec.break_even_customers(fixed_costs=1000.0, contribution_per_customer=30.0)
    assert r.computable and r.value == 34.0
    assert ec.break_even_customers(fixed_costs=1000.0, contribution_per_customer=0.0).computable is False


def test_budget_utilization_valid_and_zero_budget():
    assert ec.budget_utilization_pct(actual_spend=333.0, budget=1000.0).value == 33.3
    assert ec.budget_utilization_pct(actual_spend=100.0, budget=0.0).computable is False


def test_cac_via_trust_requires_verified_source_and_guards_zero():
    # Unverified source → non-computable (trust enforces provider verification).
    assert ec.cac_via_trust(spend=1000.0, new_customers=10.0, verified_source=False).computable is False
    # Verified + valid → computed (1000/10 = 100).
    ok = ec.cac_via_trust(spend=1000.0, new_customers=10.0, verified_source=True)
    assert ok.computable and ok.value == 100.0
    # Zero denominator guarded.
    assert ec.cac_via_trust(spend=1000.0, new_customers=0.0, verified_source=True).computable is False


# ---------------------------------------------------------------------
#  Currency inference — token match, never a substring false-positive,
#  never a silent default.
# ---------------------------------------------------------------------


def test_currency_inference_known_locations():
    assert ec.infer_currency("Mumbai, India")[0] == "INR"
    assert ec.infer_currency("Austin, TX")[0] == "USD"
    assert ec.infer_currency("London, UK")[0] == "GBP"
    assert ec.infer_currency("Dubai, UAE")[0] == "AED"


def test_currency_inference_no_false_substring_and_unknown():
    # "Austin" must NOT match the "us" token by substring.
    code, _ = ec.infer_currency("Austin")
    assert code is None  # unknown, not a guessed USD
    assert ec.infer_currency("")[0] is None
    assert ec.infer_currency(None)[0] is None
    assert ec.infer_currency("Someplace Nowhere")[0] is None


def test_parse_amount_band():
    assert ec.parse_amount_band("$100-500") == (100.0, 500.0)
    assert ec.parse_amount_band("0-10") == (0.0, 10.0)
    assert ec.parse_amount_band("$1,000-2,000") == (1000.0, 2000.0)
    assert ec.parse_amount_band("$50") == (50.0, 50.0)
    assert ec.parse_amount_band("") == (None, None)
    assert ec.parse_amount_band("n/a") == (None, None)


# ---------------------------------------------------------------------
#  Resolver — provenance, explicit period, INSUFFICIENT_EVIDENCE, status
# ---------------------------------------------------------------------


def _profile(**kw) -> SimpleNamespace:
    base = dict(
        business_location="Austin, TX", monthly_budget_band="$100-500",
        pricing="$65 full groom", primary_goal_text="200 bookings/mo",
        products=["Full groom"], services=["Bath"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _analytics() -> MarketingBrainAnalyticsSnapshot:
    return MarketingBrainAnalyticsSnapshot(
        total_leads=12, leads_7d=3, leads_30d=9, hot_leads=2, conversion_rate=0.08,
        landing_pages_published=1, total_views=100, total_submissions=8,
    )


def test_resolver_populated_with_provenance_and_period():
    res = ec.resolve_economics(profile_row=_profile(), analytics=_analytics())
    assert res.status == "populated"
    assert res.currency == "USD"  # inferred from "TX"
    assert res.period == "last 30 days"

    tiers = {i.provenance for i in res.items}
    assert ContextProvenance.USER_STATED in tiers   # budget/pricing/goal
    assert ContextProvenance.MEASURED in tiers       # conversion economics
    assert ContextProvenance.SYSTEM_INFERRED in tiers  # currency
    assert ContextProvenance.UNKNOWN in tiers        # margin/LTV/CAC/break-even

    # USER_STATED economic context never carries a confidence number.
    for i in res.items:
        if i.provenance == ContextProvenance.USER_STATED:
            assert i.confidence is None
    # Measured items carry an explicit reporting period (no silent mismatch).
    measured = [i for i in res.items if i.provenance == ContextProvenance.MEASURED]
    assert measured and all(i.status == "last 30 days" for i in measured)
    # Uncaptured quantitative metrics are INSUFFICIENT_EVIDENCE, not fabricated.
    gm = next(i for i in res.items if i.label == "Gross margin")
    assert gm.provenance == ContextProvenance.UNKNOWN and "INSUFFICIENT_EVIDENCE" in (gm.detail or "")
    assert "provenance" in res.note.lower()


def test_resolver_unknown_when_nothing_available():
    res = ec.resolve_economics(profile_row=None, analytics=None)
    assert res.status == "unknown"
    assert res.currency is None  # no location → no guessed currency
    assert all(i.provenance == ContextProvenance.UNKNOWN for i in res.items)


def test_resolver_currency_unknown_but_metrics_still_insufficient():
    # Profile present but location unknown → currency UNKNOWN, no fabrication,
    # budget still surfaced as USER_STATED, status populated.
    res = ec.resolve_economics(profile_row=_profile(business_location="Someplace"), analytics=None)
    assert res.currency is None
    assert res.status == "populated"  # budget/pricing still USER_STATED
    assert any(i.provenance == ContextProvenance.USER_STATED for i in res.items)


def test_resolver_computes_metrics_from_stored_economics():
    """Stage 2b: with persisted inputs, the resolver computes margin/LTV/break-even
    deterministically (SYSTEM_INFERRED, derived), and prefers the stored currency."""
    from aicmo.modules.business_dna.economics_schema import BusinessEconomics, EconomicValue

    def ev(v: float) -> EconomicValue:
        return EconomicValue(value=v, provenance=ContextProvenance.USER_STATED, currency="GBP")

    econ = BusinessEconomics(
        currency="GBP", reporting_period="monthly",
        price=ev(100.0), unit_cost=ev(40.0), fixed_costs=ev(6000.0),
        avg_order_value=ev(100.0), purchases_per_year=ev(4.0), lifespan_years=ev(3.0),
    )
    res = ec.resolve_economics(profile_row=_profile(), analytics=None, economics=econ)
    assert res.currency == "GBP"  # stored currency wins over location inference
    by = {i.label: i for i in res.items}

    gm = by["Gross margin"]
    assert gm.provenance == ContextProvenance.SYSTEM_INFERRED and gm.detail == "60.0%"
    # Break-even revenue = 6000 / 0.60 = 10,000.00 (currency-formatted, stored GBP).
    ber = by["Break-even revenue"]
    assert ber.provenance == ContextProvenance.SYSTEM_INFERRED and "10,000.00" in ber.detail
    # LTV uses the computed 60% margin: 100*4*3*0.6 = 720.00.
    ltv_item = by["Customer lifetime value (LTV)"]
    assert ltv_item.provenance == ContextProvenance.SYSTEM_INFERRED and "720.00" in ltv_item.detail
    # The stored inputs themselves are surfaced with their own provenance.
    assert by["Unit price"].provenance == ContextProvenance.USER_STATED
    # CAC still needs a provider-verified spend source → INSUFFICIENT.
    assert "INSUFFICIENT_EVIDENCE" in (by["Customer acquisition cost (CAC)"].detail or "")
