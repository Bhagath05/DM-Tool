"""Phase 10.2e — HTTP surface for billing.

Five endpoints. Permission split:

  Read endpoints — any tenant member can see billing status of THEIR
  workspace (every member needs to know "are we approaching a quota?"):
    GET /billing/plans
    GET /billing/subscription
    GET /billing/usage

  Sensitive — restricted to billing.manage (owner only per W1-14 seed):
    GET /billing/invoices         — invoices are PII-adjacent
    POST /billing/upgrade-request — only an owner can commit the org
                                     to a paid plan

There is NO HTTP recorder for usage_event. Inflation of usage counters
by an authenticated client would be a billing-integrity bug. Future
emitting services call `billing_service.record_usage(...)` directly.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.billing import billing_live, plan_catalog, service
from aicmo.modules.billing.payments import stripe_gateway
from aicmo.modules.billing.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    InvoiceList,
    PlanCatalog,
    PortalRequest,
    PortalResponse,
    SubscriptionRead,
    UpgradeRequest,
    UpgradeRequestResponse,
    UsageSummary,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

log = structlog.get_logger()


router = APIRouter(prefix="/billing", tags=["billing"])
# Public — the Stripe webhook carries no tenant header; it's authenticated
# by its signature, not Clerk/tenant. Mirrors the Clerk webhook split.
public_router = APIRouter(prefix="/billing", tags=["billing"])

_RequireTenant = require_tenant(brand_optional=True)
_RequireBillingManage = require_permission(
    "billing.manage", brand_optional=True
)


# ---------------------------------------------------------------------
#  Read endpoints (any tenant member)
# ---------------------------------------------------------------------


@router.get(
    "/plans",
    response_model=PlanCatalog,
    summary="Static catalog of plans (Early Access / Growth / Scale)",
)
async def get_plans(
    _tenant: TenantContext = Depends(_RequireTenant),
) -> PlanCatalog:
    """Static — same response for every caller. Frontend caches.

    Tenant-gated only because the Settings page is behind auth; the
    catalog data itself is non-sensitive."""
    return plan_catalog.get_catalog()


@router.get(
    "/subscription",
    response_model=SubscriptionRead,
    summary="Current subscription for the active org",
)
async def get_subscription(
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> SubscriptionRead:
    """Auto-provisions Early Access on first call — never 404s."""
    return await service.get_subscription(
        session, organization_id=tenant.organization_id
    )


@router.get(
    "/usage",
    response_model=UsageSummary,
    summary="Current-period usage summary, broken down by kind",
)
async def get_usage(
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> UsageSummary:
    return await service.get_usage_summary(
        session, organization_id=tenant.organization_id
    )


# ---------------------------------------------------------------------
#  Sensitive endpoints (billing.manage required → owner)
# ---------------------------------------------------------------------


@router.get(
    "/invoices",
    response_model=InvoiceList,
    summary="List invoices (empty for Early Access)",
)
async def get_invoices(
    tenant: TenantContext = Depends(_RequireBillingManage),
    session: AsyncSession = Depends(get_db),
) -> InvoiceList:
    return await service.list_invoices(
        session, organization_id=tenant.organization_id
    )


@router.post(
    "/upgrade-request",
    response_model=UpgradeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record interest in upgrading. Honest placeholder — no Stripe.",
)
async def post_upgrade_request(
    payload: UpgradeRequest,
    tenant: TenantContext = Depends(_RequireBillingManage),
    session: AsyncSession = Depends(get_db),
) -> UpgradeRequestResponse:
    """The response carries `delivery_status="manual"` — we tell the
    frontend explicitly that NO automated checkout will happen.

    Honest copy in the response body: 'We've recorded your interest.
    Our team will reach out...' — never imply a payment was processed.
    """
    try:
        return await service.request_upgrade(
            session,
            organization_id=tenant.organization_id,
            requester_user_id=tenant.user_uuid,
            payload=payload,
        )
    except service.UnknownPlan as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown plan: {exc.plan_slug}",
        )
    except service.CannotUpgradeToCurrentPlan:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You're already on this plan. No upgrade needed."
            ),
        )
    except service.CannotUpgradeToDefaultPlan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot upgrade TO the default plan — that would be a "
                "downgrade. Contact support if you need to downgrade."
            ),
        )


# ---------------------------------------------------------------------
#  Phase 1 — Stripe checkout / portal (owner-gated)
# ---------------------------------------------------------------------


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Start a Stripe-hosted Checkout Session for a plan",
)
async def post_checkout(
    payload: CheckoutRequest,
    tenant: TenantContext = Depends(_RequireBillingManage),
    session: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Returns a Stripe Checkout URL the frontend redirects to. When live
    billing is disabled (default), returns 409 so the UI falls back to the
    existing upgrade-request placeholder flow."""
    try:
        url = await billing_live.start_checkout(
            session,
            organization_id=tenant.organization_id,
            plan_slug=payload.plan_slug,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except billing_live.BillingNotLive:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Self-serve checkout isn't enabled yet — use Request upgrade.",
        )
    except service.UnknownPlan as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown or unpriced plan: {exc.plan_slug}",
        )
    except stripe_gateway.StripeNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is temporarily unavailable.",
        )
    await session.commit()
    return CheckoutResponse(url=url)


@router.post(
    "/portal",
    response_model=PortalResponse,
    summary="Open the Stripe Billing Portal for the active org",
)
async def post_portal(
    payload: PortalRequest,
    tenant: TenantContext = Depends(_RequireBillingManage),
    session: AsyncSession = Depends(get_db),
) -> PortalResponse:
    try:
        url = await billing_live.start_portal(
            session,
            organization_id=tenant.organization_id,
            return_url=payload.return_url,
        )
    except billing_live.BillingNotLive:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active subscription to manage yet.",
        )
    except stripe_gateway.StripeNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is temporarily unavailable.",
        )
    return PortalResponse(url=url)


# ---------------------------------------------------------------------
#  Phase 1 — Stripe webhook (PUBLIC, signature-verified, idempotent)
# ---------------------------------------------------------------------


@public_router.post(
    "/webhooks/stripe",
    summary="Stripe webhook receiver (signature-verified, idempotent)",
    status_code=status.HTTP_200_OK,
)
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verifies the Stripe signature, then syncs subscription/invoice
    state. Returns 200 for verified events (even unhandled types) so
    Stripe stops retrying; 400 for an invalid signature (dropped)."""
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing signature")
    payload = await request.body()
    try:
        event = stripe_gateway.construct_event(payload, sig)
    except stripe_gateway.StripeNotConfigured:
        # Webhook secret not set → receiver is effectively disabled.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook not configured",
        )
    except Exception:  # noqa: BLE001 — bad signature / malformed payload → drop
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid signature"
        )

    result = await billing_live.handle_stripe_event(session, dict(event))
    await session.commit()
    return {"status": result}
