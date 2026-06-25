"""Phase 10.2e — Pydantic schemas for billing.

Hard rule (mirrored across all 10.2 phases): no schema exposes Stripe
ids (`external_subscription_id`, `external_customer_id`,
`external_invoice_id`) or any other secret. Those exist in the DB so
the future Stripe wiring has somewhere to land — but the API never
ships them. The reflection guard in `tests/billing/test_schemas.py`
enforces.

`hosted_invoice_url` IS exposed — that's the public Stripe-hosted page
the founder needs to view the actual invoice document. Distinct from
the API-side `external_invoice_id` (which is a server-only correlation
handle).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------
#  Enums — lock-step with migration 0027 CHECK constraints
# ---------------------------------------------------------------------

PlanSlug = Literal["early_access", "growth", "scale"]

SubscriptionStatus = Literal["active", "trialing", "past_due", "canceled"]

InvoiceStatus = Literal["draft", "open", "paid", "void", "uncollectible"]

UsageKind = Literal[
    "csv_upload",
    "lead_processed",
    "ai_recommendation",
    "creative_analysis",
    "campaign_analysis",
    # Phase 1 — product-metered kinds the DB plan quotas are defined against.
    "generation",  # content / ad / visual / bundle generation
    "campaign",    # campaign plan generation
    "lead",        # lead captured / processed
]

# The three kinds that carry plan quotas (the DB-configurable limits).
METERED_KINDS: tuple[UsageKind, ...] = ("generation", "campaign", "lead")

UpgradeRequestStatus = Literal[
    "pending", "contacted", "converted", "declined"
]

# How a CTA on the Settings → Billing page should behave for a given plan.
PlanCtaKind = Literal["current", "upgrade", "contact_sales", "unavailable"]

# Status of the plan in the catalog — drives "Available now" vs "Coming soon".
PlanAvailability = Literal["current", "upcoming"]


# ---------------------------------------------------------------------
#  Plan catalog descriptors
# ---------------------------------------------------------------------


class PlanQuota(BaseModel):
    """One row in a plan's quota table.

    `limit` of None means "unlimited" — Early Access uses None across
    the board. A non-None integer is the per-period (monthly) cap.
    """

    model_config = ConfigDict(extra="forbid")

    kind: UsageKind
    display_name: str
    limit: int | None = Field(
        description="None = unlimited. Integer = monthly cap in events.",
    )


class PlanDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: PlanSlug
    display_name: str
    tagline: str = Field(
        description=(
            "One-line marketing line shown under the plan card title. "
            "Founder-facing copy — keep plain-language, no jargon."
        ),
    )
    description: str
    monthly_price_cents: int | None = Field(
        description=(
            "Price in minor units. None for Early Access (free / "
            "by-invite) and Scale (custom / contact sales)."
        ),
    )
    currency: str = Field(min_length=3, max_length=3)
    quotas: list[PlanQuota]
    availability: PlanAvailability
    is_default: bool = Field(
        description="True for the plan auto-provisioned on org creation.",
    )
    cta_label: str = Field(
        description="Copy for the action button on the plan card.",
    )
    cta_kind: PlanCtaKind = Field(
        description=(
            "Drives the button's behaviour: 'current' = no-op + checkmark, "
            "'upgrade' = POST /billing/upgrade-request, "
            "'contact_sales' = same as upgrade but copy varies, "
            "'unavailable' = greyed out."
        ),
    )
    feature_highlights: list[str] = Field(
        description="Plain-language capability bullets for the plan card.",
    )


class PlanCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plans: list[PlanDescriptor]


# ---------------------------------------------------------------------
#  Subscription
# ---------------------------------------------------------------------


class SubscriptionRead(BaseModel):
    """Public projection of the org's current subscription.

    NOTE: external_*_id fields are deliberately absent — those are
    Stripe correlation handles and don't belong on the API.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    plan_slug: PlanSlug
    plan_display_name: str = Field(
        description="Pre-resolved from the catalog so the UI doesn't have to look it up.",
    )
    status: SubscriptionStatus
    period_start: datetime | None
    period_end: datetime | None
    trial_ends_at: datetime | None
    canceled_at: datetime | None
    cancel_at_period_end: bool
    is_on_default_plan: bool = Field(
        description="True if the org is on the default plan (Early Access).",
    )
    is_paid_plan: bool = Field(
        description=(
            "True for Growth + Scale once they ship. Drives 'Manage "
            "payment method' affordance — hidden for Early Access."
        ),
    )
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------
#  Usage
# ---------------------------------------------------------------------


class UsageBreakdownCell(BaseModel):
    """One row in the usage summary table.

    `limit` echoes the plan's quota so the UI can render
    "Recommendations: 42 of 1,000" without a second lookup.
    """

    model_config = ConfigDict(extra="forbid")

    kind: UsageKind
    display_name: str
    used: int
    limit: int | None
    percent_used: float | None = Field(
        description="None when limit is None (unlimited). 0..100 otherwise.",
    )


class UsageSummary(BaseModel):
    """Settings → Billing → Usage section, one call.

    Period boundaries are returned even when null (Early Access has no
    period) so the UI can render "All-time usage" vs "Jun 1 – Jun 30."
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    plan_slug: PlanSlug
    period_start: datetime | None
    period_end: datetime | None
    cells: list[UsageBreakdownCell]


# ---------------------------------------------------------------------
#  Invoices
# ---------------------------------------------------------------------


class InvoiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    number: str
    status: InvoiceStatus
    amount_total_cents: int
    currency: str
    period_start: datetime
    period_end: datetime
    due_at: datetime | None
    paid_at: datetime | None
    hosted_invoice_url: str | None = Field(
        description=(
            "Stripe-hosted public invoice page. Null in dev / when the "
            "invoice isn't backed by real billing."
        ),
    )
    created_at: datetime


class InvoiceList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoices: list[InvoiceRead]


# ---------------------------------------------------------------------
#  Upgrade-request (honest placeholder)
# ---------------------------------------------------------------------


class UpgradeRequest(BaseModel):
    """POST /billing/upgrade-request body."""

    model_config = ConfigDict(extra="forbid")

    requested_plan_slug: PlanSlug
    note: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional founder context (e.g. 'need this by Q3').",
    )


class UpgradeRequestResponse(BaseModel):
    """Returned from POST /billing/upgrade-request.

    The `delivery_status: 'manual'` flag is the honest part: we tell
    the frontend that no checkout will happen — a human will follow up.
    The UI should render copy like 'We've recorded your interest. Our
    team will reach out within 2 business days.' — never imply that
    a payment was processed.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    requested_plan_slug: PlanSlug
    current_plan_slug: PlanSlug
    status: UpgradeRequestStatus
    delivery_status: Literal["manual"] = Field(
        default="manual",
        description=(
            "Phase 10.2e ships without Stripe — every upgrade request "
            "is delivered to humans, not a checkout flow. Frozen at "
            "'manual' until Stripe lands."
        ),
    )
    message: str = Field(
        description=(
            "Founder-facing copy the UI renders verbatim. Set "
            "server-side so we can A/B the wording without a deploy."
        ),
    )
    created_at: datetime


# ---------------------------------------------------------------------
#  Phase 1 — Stripe checkout / portal
# ---------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """POST /billing/checkout body. plan_slug is validated against the
    DB plan table server-side (not a Literal — plans are DB-configurable)."""

    model_config = ConfigDict(extra="forbid")

    plan_slug: str = Field(min_length=1, max_length=32)
    success_url: str = Field(min_length=1, max_length=2048)
    cancel_url: str = Field(min_length=1, max_length=2048)


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str


class PortalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    return_url: str = Field(min_length=1, max_length=2048)


class PortalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
