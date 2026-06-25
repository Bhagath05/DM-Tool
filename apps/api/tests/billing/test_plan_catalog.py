"""Phase 10.2e — Plan catalog correctness.

Pin every visible field on the 3-plan catalog. Founder-facing copy is
sensitive — a copy edit shouldn't slip through silently and a CTA
that goes from 'current' to 'upgrade' is a UX regression that breaks
the Settings → Billing page.
"""

from __future__ import annotations

from aicmo.modules.billing import plan_catalog


# ---------------------------------------------------------------------
#  Surface
# ---------------------------------------------------------------------


def test_exactly_three_plans() -> None:
    slugs = [p.slug for p in plan_catalog.get_catalog().plans]
    assert slugs == ["early_access", "growth", "scale"]


def test_every_plan_has_display_copy() -> None:
    for p in plan_catalog.get_catalog().plans:
        assert p.display_name, f"{p.slug} missing display_name"
        assert p.tagline and len(p.tagline) >= 20, (
            f"{p.slug} tagline too short to be useful"
        )
        assert p.description and len(p.description) >= 30
        assert p.feature_highlights, f"{p.slug} has no feature_highlights"


def test_every_plan_carries_all_five_usage_quotas() -> None:
    """Every plan must enumerate ALL 5 usage kinds — even if the
    limit is None. Otherwise the UI's per-kind row would render a
    blank cell for the missing kind, which looks like a bug."""
    expected_kinds = {
        "csv_upload",
        "lead_processed",
        "ai_recommendation",
        "creative_analysis",
        "campaign_analysis",
    }
    for p in plan_catalog.get_catalog().plans:
        kinds = {q.kind for q in p.quotas}
        assert kinds == expected_kinds, (
            f"{p.slug} quota set drifted: missing={expected_kinds - kinds}, "
            f"extra={kinds - expected_kinds}"
        )


# ---------------------------------------------------------------------
#  Default plan — exactly one
# ---------------------------------------------------------------------


def test_exactly_one_plan_is_default() -> None:
    """Multiple defaults would make `ensure_subscription` ambiguous —
    pin to one."""
    defaults = [p for p in plan_catalog.get_catalog().plans if p.is_default]
    assert len(defaults) == 1, (
        f"expected exactly one default plan, got {[p.slug for p in defaults]}"
    )


def test_early_access_is_the_default() -> None:
    """Spec: 'Early Access — Current users — Unlimited access for now'.
    Pin that early_access IS the default — if a future PR makes Growth
    the default by mistake, every newly-provisioned org gets a paid
    plan with no payment method on file."""
    assert plan_catalog.default_plan_slug() == "early_access"


# ---------------------------------------------------------------------
#  Early Access: unlimited
# ---------------------------------------------------------------------


def test_early_access_all_quotas_unlimited() -> None:
    """User spec: Early Access = Unlimited access for now. None ==
    unlimited in the schema."""
    ea = plan_catalog.descriptor_for("early_access")
    assert ea is not None
    for q in ea.quotas:
        assert q.limit is None, (
            f"early_access {q.kind} has limit={q.limit}; "
            "must be None (unlimited) per spec"
        )


def test_early_access_has_no_price() -> None:
    """No paid checkout for Early Access. None price + no Stripe
    integration = honest 'free while we figure pricing out' state."""
    ea = plan_catalog.descriptor_for("early_access")
    assert ea is not None
    assert ea.monthly_price_cents is None


def test_early_access_cta_is_current() -> None:
    """Settings page button reads 'Your current plan' (no-op) for the
    org that's on it. Changing this to 'upgrade' would let the founder
    request to upgrade to the plan they're already on."""
    ea = plan_catalog.descriptor_for("early_access")
    assert ea is not None
    assert ea.cta_kind == "current"


# ---------------------------------------------------------------------
#  Growth / Scale: upcoming
# ---------------------------------------------------------------------


def test_growth_and_scale_are_upcoming() -> None:
    """Neither paid plan is available yet — both surface as 'Coming
    soon'. When a plan goes live this test changes intentionally."""
    for slug in ("growth", "scale"):
        d = plan_catalog.descriptor_for(slug)
        assert d is not None and d.availability == "upcoming", (
            f"{slug} availability={d.availability if d else None}"
        )


def test_growth_quotas_are_finite() -> None:
    """Growth is the future paid plan; its limits should be real ints
    so the UI can render a progress bar without special-casing
    None. (Early Access is the only None-everywhere plan.)"""
    growth = plan_catalog.descriptor_for("growth")
    assert growth is not None
    for q in growth.quotas:
        assert q.limit is not None and q.limit > 0, (
            f"growth {q.kind} has non-finite limit {q.limit}"
        )


def test_scale_quotas_are_higher_than_growth() -> None:
    """Tier ordering: Scale > Growth on every dimension. Catches
    accidental copy-paste regression."""
    growth = plan_catalog.descriptor_for("growth")
    scale = plan_catalog.descriptor_for("scale")
    assert growth is not None and scale is not None
    growth_q = {q.kind: q.limit for q in growth.quotas}
    scale_q = {q.kind: q.limit for q in scale.quotas}
    for kind, g_limit in growth_q.items():
        s_limit = scale_q[kind]
        assert g_limit is not None and s_limit is not None
        assert s_limit > g_limit, (
            f"Scale {kind}={s_limit} not > Growth {kind}={g_limit}"
        )


def test_scale_cta_is_contact_sales() -> None:
    """Scale = custom pricing → contact sales, not checkout."""
    scale = plan_catalog.descriptor_for("scale")
    assert scale is not None
    assert scale.cta_kind == "contact_sales"


def test_no_upcoming_plan_advertises_an_invented_price() -> None:
    """Phase 10.2e has no real Stripe wiring. Showing a confident
    price would imply a checkout that doesn't exist. Both Growth and
    Scale must have monthly_price_cents=None until Stripe ships."""
    for slug in ("growth", "scale"):
        d = plan_catalog.descriptor_for(slug)
        assert d is not None and d.monthly_price_cents is None, (
            f"{slug} advertises a price ({d.monthly_price_cents if d else None}) "
            "but Phase 10.2e has no checkout to back it"
        )


# ---------------------------------------------------------------------
#  Lookups
# ---------------------------------------------------------------------


def test_descriptor_for_unknown_returns_none() -> None:
    assert plan_catalog.descriptor_for("not-a-plan") is None


def test_quota_for_known_plan_kind() -> None:
    assert plan_catalog.quota_for("early_access", "csv_upload") is None
    assert plan_catalog.quota_for("growth", "ai_recommendation") == 1_000


def test_quota_for_unknown_returns_none() -> None:
    """Defensive: unknown plan/kind returns None (unlimited) rather
    than raising. Caller will surface as unrestricted, which is
    safer than 500-ing the whole usage endpoint."""
    assert plan_catalog.quota_for("not-a-plan", "csv_upload") is None


def test_all_usage_kinds_returns_five_in_canonical_order() -> None:
    """Frontend snapshots iterate this list — pin order."""
    kinds = plan_catalog.all_usage_kinds()
    assert kinds == [
        "csv_upload",
        "lead_processed",
        "ai_recommendation",
        "creative_analysis",
        "campaign_analysis",
    ]
