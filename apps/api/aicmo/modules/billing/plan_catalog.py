"""Phase 10.2e — Plan catalog (static, code-defined).

Single source of truth for the 3 plans. Mirrors the pattern used by
`notifications/catalog.py` and `team/role_catalog.py`.

The DB CHECK constraint in migration 0027 mirrors the slug list;
editing either in isolation drifts the system. Always update both
in the same PR.

Phase 10.2e ships:
  - early_access — current users, unlimited, default-provisioned
  - growth       — future paid plan (placeholder; quotas exist for UI)
  - scale        — future enterprise plan (custom pricing; contact sales)

When Stripe lands, this file changes shape: prices move to Stripe price
ids + a server-side resolver. The interface (`get_catalog`,
`descriptor_for`) stays the same so the frontend doesn't have to
re-render.
"""

from __future__ import annotations

from aicmo.modules.billing.schemas import (
    PlanCatalog,
    PlanDescriptor,
    PlanQuota,
    UsageKind,
)


# ---------------------------------------------------------------------
#  Per-kind display copy — reused across plan quotas + usage cells
# ---------------------------------------------------------------------

USAGE_DISPLAY_NAMES: dict[UsageKind, str] = {
    "csv_upload": "CSV uploads",
    "lead_processed": "Leads processed",
    "ai_recommendation": "AI recommendations generated",
    "creative_analysis": "Creative analyses performed",
    "campaign_analysis": "Campaigns analyzed",
}


def _quota(kind: UsageKind, limit: int | None) -> PlanQuota:
    """Convenience factory — keeps each plan's quota block tight."""
    return PlanQuota(
        kind=kind, display_name=USAGE_DISPLAY_NAMES[kind], limit=limit
    )


# ---------------------------------------------------------------------
#  The 3 plans
# ---------------------------------------------------------------------

_EARLY_ACCESS = PlanDescriptor(
    slug="early_access",
    display_name="Early Access",
    tagline="Everything unlocked while you help us shape the product.",
    description=(
        "Full access to every feature. No usage limits, no payment "
        "method required. You're trading early-adopter feedback for "
        "unrestricted use — this plan goes away once we ship paid "
        "tiers."
    ),
    monthly_price_cents=None,  # free / by-invite
    currency="USD",
    quotas=[
        _quota("csv_upload", None),
        _quota("lead_processed", None),
        _quota("ai_recommendation", None),
        _quota("creative_analysis", None),
        _quota("campaign_analysis", None),
    ],
    availability="current",
    is_default=True,
    cta_label="Your current plan",
    cta_kind="current",
    feature_highlights=[
        "Unlimited usage across every feature",
        "Direct line to the founding team for feedback + feature requests",
        "All future paid features included while you're on Early Access",
    ],
)

# Growth quotas: deliberately set non-trivially high so the UI can
# render real "X of Y" progress bars during demos without rolling
# over instantly. Numbers are placeholders — Stripe wiring will pull
# the real source of truth from a Product config service / Stripe
# product metadata later.
_GROWTH = PlanDescriptor(
    slug="growth",
    display_name="Growth",
    tagline="For founders running paid campaigns and ready to scale.",
    description=(
        "Generous limits across uploads, leads, and AI recommendations. "
        "Designed for businesses spending real money on ads who want "
        "the platform analysing every campaign automatically."
    ),
    monthly_price_cents=None,  # placeholder; real price set when Stripe ships
    currency="USD",
    quotas=[
        _quota("csv_upload", 200),
        _quota("lead_processed", 10_000),
        _quota("ai_recommendation", 1_000),
        _quota("creative_analysis", 500),
        _quota("campaign_analysis", 200),
    ],
    availability="upcoming",
    is_default=False,
    cta_label="Notify me when Growth launches",
    cta_kind="upgrade",
    feature_highlights=[
        "10,000 leads processed per month",
        "1,000 AI recommendations per month",
        "Email + Slack notifications when delivery launches",
        "Priority support from the team",
    ],
)

_SCALE = PlanDescriptor(
    slug="scale",
    display_name="Scale",
    tagline="For agencies and teams managing many brands.",
    description=(
        "Custom limits, dedicated onboarding, and Service Level "
        "guarantees. Built for teams who need the platform to "
        "underwrite their own work."
    ),
    monthly_price_cents=None,  # custom — always contact sales
    currency="USD",
    quotas=[
        # Higher than Growth, sized for agency-level workloads.
        _quota("csv_upload", 2_000),
        _quota("lead_processed", 100_000),
        _quota("ai_recommendation", 10_000),
        _quota("creative_analysis", 5_000),
        _quota("campaign_analysis", 2_000),
    ],
    availability="upcoming",
    is_default=False,
    cta_label="Contact sales",
    cta_kind="contact_sales",
    feature_highlights=[
        "Custom usage limits sized to your workload",
        "Dedicated onboarding + ongoing strategic sessions",
        "Service Level Agreement on uptime + response time",
        "Multi-brand workspace management at scale",
    ],
)

_PLANS: tuple[PlanDescriptor, ...] = (_EARLY_ACCESS, _GROWTH, _SCALE)


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def get_catalog() -> PlanCatalog:
    """Return the static catalog — same response for every caller."""
    return PlanCatalog(plans=list(_PLANS))


def descriptor_for(slug: str) -> PlanDescriptor | None:
    """Look up one plan descriptor. Returns None for unknown slug."""
    for p in _PLANS:
        if p.slug == slug:
            return p
    return None


def default_plan_slug() -> str:
    """Slug of the plan auto-provisioned on org creation.

    Pinned by `tests/billing/test_plan_catalog.py` to ensure exactly
    one plan carries is_default=True (would-be ambiguity is a bug)."""
    for p in _PLANS:
        if p.is_default:
            return p.slug
    raise RuntimeError(
        "No default plan in catalog — billing module is misconfigured."
    )


def quota_for(plan_slug: str, kind: UsageKind) -> int | None:
    """Look up the per-period limit for (plan, kind). None = unlimited.

    Used by the usage summary to populate the `limit` column without
    the caller re-walking the catalog.
    """
    plan = descriptor_for(plan_slug)
    if plan is None:
        return None
    for q in plan.quotas:
        if q.kind == kind:
            return q.limit
    return None


def all_usage_kinds() -> list[UsageKind]:
    """Canonical iteration order — matches USAGE_DISPLAY_NAMES insertion.
    The usage summary endpoint always returns cells in this order so
    the frontend snapshot is stable."""
    return list(USAGE_DISPLAY_NAMES.keys())
