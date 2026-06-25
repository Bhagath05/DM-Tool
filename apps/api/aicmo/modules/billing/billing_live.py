"""Live billing — Stripe checkout/portal/webhook + usage quota gate.

Phase 1. Kept separate from the Phase-10.2e `service.py` (plan reads +
the honest-placeholder upgrade flow) so the live path is clearly
isolated and flag-gated. Nothing here changes behavior unless
`billing_live_enabled` / `billing_enforce_limits` are turned on.

Quota model:
  - `check_quota`  — pure read: used vs the DB-configured monthly limit.
  - `enforce_quota`— soft gate called BEFORE a generation. Blocks (402)
                     ONLY when `billing_enforce_limits` is true AND the
                     org is over limit. Default off → record-only, the
                     caller still gets the QuotaStatus to show a warning.
  - `record_metered` — emit a usage_event AFTER a generation (same TX),
                     via the existing single write path `service.record_usage`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.billing import plan_service, service
from aicmo.modules.billing.models import Invoice, Subscription, UsageEvent
from aicmo.modules.billing.payments import stripe_gateway
from aicmo.modules.billing.plan_models import Plan, StripeEvent
from aicmo.modules.billing.schemas import UsageKind

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Quota
# ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    kind: str
    used: int
    limit: int | None   # None = unlimited
    remaining: int | None
    over: bool
    near: bool          # ≥80% used — drives a soft warning in the UI


def _period_start(sub: Subscription) -> datetime:
    if sub.period_start is not None:
        return sub.period_start
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def check_quota(
    session: AsyncSession, *, organization_id: uuid.UUID, kind: UsageKind
) -> QuotaStatus:
    """Read-only usage-vs-limit for one metered kind, current period."""
    sub = await service.ensure_subscription(
        session, organization_id=organization_id
    )
    limit = await plan_service.quota_for(session, sub.plan_slug, kind)
    if limit is None:
        return QuotaStatus(kind, used=0, limit=None, remaining=None, over=False, near=False)

    start = _period_start(sub)
    stmt = (
        select(func.coalesce(func.sum(UsageEvent.quantity), 0))
        .where(UsageEvent.organization_id == organization_id)
        .where(UsageEvent.kind == kind)
        .where(UsageEvent.occurred_at >= start)
    )
    if sub.period_end is not None:
        stmt = stmt.where(UsageEvent.occurred_at < sub.period_end)
    used = int((await session.execute(stmt)).scalar_one())
    remaining = max(0, limit - used)
    return QuotaStatus(
        kind=kind,
        used=used,
        limit=limit,
        remaining=remaining,
        over=used >= limit,
        near=limit > 0 and used >= (limit * 0.8),
    )


async def enforce_quota(
    session: AsyncSession, *, organization_id: uuid.UUID, kind: UsageKind
) -> QuotaStatus:
    """Soft gate. Returns the QuotaStatus always. Raises 402 ONLY when
    enforcement is enabled AND the org is over limit. With enforcement
    off (default), never blocks — the caller shows a warning instead.

    Fails OPEN: any error computing the quota allows the generation
    (billing must never 500 a core feature)."""
    try:
        st = await check_quota(session, organization_id=organization_id, kind=kind)
    except Exception as e:  # noqa: BLE001 — never block generation on a metering error
        log.warning("billing.quota_check_failed", kind=kind, error=str(e))
        return QuotaStatus(kind, used=0, limit=None, remaining=None, over=False, near=False)

    if st.over and get_settings().billing_enforce_limits:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "quota_exceeded",
                "kind": kind,
                "used": st.used,
                "limit": st.limit,
                "message": (
                    f"You've reached your monthly {kind} limit ({st.limit}). "
                    "Upgrade your plan to keep going."
                ),
            },
        )
    return st


async def record_metered(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kind: UsageKind,
    user_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    quantity: int = 1,
    metadata: dict | None = None,
) -> None:
    """Emit a usage_event via the existing single write path. Best-effort:
    a metering failure never blocks the user's generation."""
    try:
        await service.record_usage(
            session,
            organization_id=organization_id,
            kind=kind,
            quantity=quantity,
            user_id=user_id,
            brand_id=brand_id,
            metadata=metadata or {},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("billing.record_usage_failed", kind=kind, error=str(e))


# ---------------------------------------------------------------------
#  Stripe checkout / portal
# ---------------------------------------------------------------------


class BillingNotLive(Exception):
    """Live billing is disabled — caller returns 409 + the placeholder flow."""


async def start_checkout(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    plan_slug: str,
    success_url: str,
    cancel_url: str,
    email: str | None = None,
    name: str | None = None,
) -> str:
    """Create a Stripe Checkout Session for `plan_slug`; return its URL."""
    if not get_settings().billing_live_enabled:
        raise BillingNotLive()
    plan = await plan_service.get_plan(session, plan_slug)
    if plan is None or not plan.stripe_price_id:
        raise service.UnknownPlan(plan_slug)

    sub = await service.ensure_subscription(session, organization_id=organization_id)
    customer_id = stripe_gateway.create_or_get_customer(
        organization_id=organization_id,
        email=email,
        name=name,
        existing_customer_id=sub.external_customer_id,
    )
    if sub.external_customer_id != customer_id:
        db_sub = await _load_sub(session, organization_id)
        db_sub.external_customer_id = customer_id
        await session.flush()

    return stripe_gateway.create_checkout_session(
        organization_id=organization_id,
        plan_slug=plan_slug,
        price_id=plan.stripe_price_id,
        customer_id=customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
    )


async def start_portal(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    return_url: str,
) -> str:
    if not get_settings().billing_live_enabled:
        raise BillingNotLive()
    sub = await service.ensure_subscription(session, organization_id=organization_id)
    if not sub.external_customer_id:
        raise BillingNotLive()  # no Stripe customer yet → nothing to manage
    return stripe_gateway.create_billing_portal_session(
        customer_id=sub.external_customer_id, return_url=return_url
    )


# ---------------------------------------------------------------------
#  Webhook → DB sync (idempotent, signature-verified upstream)
# ---------------------------------------------------------------------


async def _load_sub(session: AsyncSession, org_id: uuid.UUID) -> Subscription:
    return (
        await session.execute(
            select(Subscription).where(Subscription.organization_id == org_id)
        )
    ).scalar_one()


async def _sub_by_customer(session: AsyncSession, customer_id: str) -> Subscription | None:
    return (
        await session.execute(
            select(Subscription).where(
                Subscription.external_customer_id == customer_id
            )
        )
    ).scalar_one_or_none()


async def handle_stripe_event(session: AsyncSession, event: dict) -> str:
    """Process a VERIFIED Stripe event idempotently. Returns a short
    status string ('processed' | 'duplicate' | 'ignored').

    Signature verification happens in the router via
    stripe_gateway.construct_event BEFORE this is called.
    """
    event_id = event.get("id")
    event_type = event.get("type", "")
    if not event_id:
        return "ignored"

    # Idempotency: claim the event id first. A duplicate delivery hits
    # the PK and is a no-op.
    existing = await session.get(StripeEvent, event_id)
    if existing is not None:
        return "duplicate"
    session.add(StripeEvent(event_id=event_id, type=event_type))
    await session.flush()

    obj = (event.get("data") or {}).get("object") or {}
    handled = await _dispatch(session, event_type, obj)

    ev = await session.get(StripeEvent, event_id)
    if ev is not None:
        ev.processed_at = datetime.now(timezone.utc)
    return "processed" if handled else "ignored"


async def _dispatch(session: AsyncSession, event_type: str, obj: dict) -> bool:
    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await _sync_subscription(session, obj, deleted=event_type.endswith("deleted"))
        return True
    if event_type == "checkout.session.completed":
        await _sync_checkout_completed(session, obj)
        return True
    if event_type in ("invoice.paid", "invoice.payment_failed"):
        await _sync_invoice(session, obj, paid=event_type == "invoice.paid")
        return True
    return False  # unhandled event type — logged + acked, not an error


def _ts(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


async def _sync_subscription(session: AsyncSession, obj: dict, *, deleted: bool) -> None:
    customer_id = obj.get("customer")
    sub = await _sub_by_customer(session, customer_id) if customer_id else None
    if sub is None:
        log.warning("billing.webhook.sub_no_match", customer=customer_id)
        return
    sub.external_subscription_id = obj.get("id") or sub.external_subscription_id
    if deleted:
        sub.status = "canceled"
        sub.canceled_at = datetime.now(timezone.utc)
    else:
        sub.status = obj.get("status") or sub.status
        sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        sub.period_start = _ts(obj.get("current_period_start")) or sub.period_start
        sub.period_end = _ts(obj.get("current_period_end")) or sub.period_end
        plan_slug = (obj.get("metadata") or {}).get("plan_slug")
        if plan_slug:
            sub.plan_slug = plan_slug
    await session.flush()


async def _sync_checkout_completed(session: AsyncSession, obj: dict) -> None:
    customer_id = obj.get("customer")
    org_ref = obj.get("client_reference_id") or (obj.get("metadata") or {}).get(
        "organization_id"
    )
    sub = None
    if customer_id:
        sub = await _sub_by_customer(session, customer_id)
    if sub is None and org_ref:
        try:
            sub = await _load_sub(session, uuid.UUID(org_ref))
        except Exception:  # noqa: BLE001
            sub = None
    if sub is None:
        log.warning("billing.webhook.checkout_no_match", customer=customer_id)
        return
    sub.external_customer_id = customer_id or sub.external_customer_id
    sub.external_subscription_id = obj.get("subscription") or sub.external_subscription_id
    plan_slug = (obj.get("metadata") or {}).get("plan_slug")
    if plan_slug:
        sub.plan_slug = plan_slug
    sub.status = "active"
    await session.flush()


async def _sync_invoice(session: AsyncSession, obj: dict, *, paid: bool) -> None:
    customer_id = obj.get("customer")
    sub = await _sub_by_customer(session, customer_id) if customer_id else None
    if sub is None:
        log.warning("billing.webhook.invoice_no_match", customer=customer_id)
        return
    external_id = obj.get("id")
    existing = (
        await session.execute(
            select(Invoice).where(Invoice.external_invoice_id == external_id)
        )
    ).scalar_one_or_none()
    inv = existing or Invoice(
        organization_id=sub.organization_id,
        subscription_id=sub.id,
        external_invoice_id=external_id,
        number=obj.get("number") or external_id or "—",
        amount_total_cents=int(obj.get("amount_due") or obj.get("total") or 0),
        currency=(obj.get("currency") or "usd").upper(),
        period_start=_ts((obj.get("lines", {}).get("data", [{}]) or [{}])[0].get("period", {}).get("start"))
        or datetime.now(timezone.utc),
        period_end=_ts((obj.get("lines", {}).get("data", [{}]) or [{}])[0].get("period", {}).get("end"))
        or datetime.now(timezone.utc),
        status="paid" if paid else "open",
    )
    inv.status = "paid" if paid else "open"
    inv.hosted_invoice_url = obj.get("hosted_invoice_url") or inv.hosted_invoice_url
    if paid:
        inv.paid_at = datetime.now(timezone.utc)
    if existing is None:
        session.add(inv)
    await session.flush()
