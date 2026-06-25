"""Phase 10.2e — Billing service layer.

Public operations:

  ensure_subscription(org_id)        — lazy-provision Early Access
  get_subscription(org_id)           — returns SubscriptionRead (calls ensure)
  request_upgrade(...)               — record interest; honest placeholder
  record_usage(...)                  — single-write path; INTERNAL Python API
  get_usage_summary(org_id)          — aggregate counts by kind for period
  list_invoices(org_id)              — empty for Early Access

Boundary rules:

  - `record_usage` is the ONLY write path to `usage_event`. Every
    future emitting service (CSV ingest, AI recommender, etc.) calls
    THIS function — never inserts directly. Same single-write-path
    pattern the security module uses for security_event.

  - `get_subscription` ALWAYS calls `ensure_subscription` first. The
    Early Access sub auto-materialises on first read so the founder's
    Settings → Billing page never 404s. This is the lazy-provision
    decision documented in the migration file.

  - The upgrade-request path is intentionally honest. No fake checkout
    URL, no `delivery_status: "automatic"`. The schema literal
    `delivery_status="manual"` is frozen until Stripe ships.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.billing import plan_catalog
from aicmo.modules.billing.models import (
    BillingUpgradeRequest,
    Invoice,
    Subscription,
    UsageEvent,
)
from aicmo.modules.billing.schemas import (
    InvoiceList,
    InvoiceRead,
    SubscriptionRead,
    UpgradeRequest,
    UpgradeRequestResponse,
    UsageBreakdownCell,
    UsageKind,
    UsageSummary,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Constants — pinned by tests
# ---------------------------------------------------------------------

# Copy returned in the UpgradeRequestResponse. Set here (not in the
# router) so we can iterate wording without redeploying.
UPGRADE_REQUEST_MESSAGE = (
    "We've recorded your interest in upgrading. Our team will reach out "
    "within 2 business days to walk you through the plan and set things "
    "up. No payment has been taken."
)


# ---------------------------------------------------------------------
#  Exceptions
# ---------------------------------------------------------------------


class UnknownPlan(Exception):
    """Requested plan slug not in the catalog."""

    def __init__(self, plan_slug: str) -> None:
        super().__init__(plan_slug)
        self.plan_slug = plan_slug


class CannotUpgradeToCurrentPlan(Exception):
    """Founder requested an upgrade to the plan they're already on."""


class CannotUpgradeToDefaultPlan(Exception):
    """Trying to 'upgrade' to Early Access from a higher plan — a
    paid-to-free move is a downgrade flow, not an upgrade. Surfaced
    as 400 so the UI knows to route to the downgrade affordance
    (which we don't ship in 10.2e)."""


# ---------------------------------------------------------------------
#  Subscriptions
# ---------------------------------------------------------------------


async def ensure_subscription(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> Subscription:
    """Return the org's subscription, lazy-provisioning Early Access on
    first read. Idempotent under concurrent calls via the partial
    UNIQUE on `subscription.organization_id`."""
    stmt = select(Subscription).where(
        Subscription.organization_id == organization_id
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    # Provision the default plan.
    default_slug = plan_catalog.default_plan_slug()
    row = Subscription(
        organization_id=organization_id,
        plan_slug=default_slug,
        status="active",
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Race: another concurrent request created it. Re-query and
        # return the winner.
        await session.rollback()
        return (await session.execute(stmt)).scalar_one()

    log.info(
        "billing.subscription.provisioned",
        organization_id=str(organization_id),
        plan_slug=default_slug,
    )
    return row


async def get_subscription(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> SubscriptionRead:
    """Read-side projection. Auto-provisions on first call."""
    sub = await ensure_subscription(
        session, organization_id=organization_id
    )
    return _to_subscription_read(sub)


# ---------------------------------------------------------------------
#  Upgrade requests (honest placeholder)
# ---------------------------------------------------------------------


async def request_upgrade(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requester_user_id: uuid.UUID | None,
    payload: UpgradeRequest,
) -> UpgradeRequestResponse:
    """Record an upgrade request. Returns a frozen `delivery_status:
    "manual"` response — never implies a payment was taken."""
    descriptor = plan_catalog.descriptor_for(payload.requested_plan_slug)
    if descriptor is None:
        raise UnknownPlan(payload.requested_plan_slug)

    if descriptor.is_default:
        # Downgrade-to-Early-Access path; reject cleanly.
        raise CannotUpgradeToDefaultPlan()

    # Resolve current plan (auto-provisions Early Access if needed).
    sub = await ensure_subscription(
        session, organization_id=organization_id
    )
    if sub.plan_slug == payload.requested_plan_slug:
        raise CannotUpgradeToCurrentPlan()

    row = BillingUpgradeRequest(
        organization_id=organization_id,
        requested_by_user_id=requester_user_id,
        requested_plan_slug=payload.requested_plan_slug,
        current_plan_slug=sub.plan_slug,
        status="pending",
        note=payload.note,
    )
    session.add(row)
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=requester_user_id or uuid.UUID(int=0),
        action="billing.upgrade_requested",
        target_type="upgrade_request",
        target_id=row.id,
        after={
            "requested_plan_slug": payload.requested_plan_slug,
            "current_plan_slug": sub.plan_slug,
        },
    )

    return UpgradeRequestResponse(
        id=row.id,
        organization_id=row.organization_id,
        requested_plan_slug=row.requested_plan_slug,  # type: ignore[arg-type]
        current_plan_slug=row.current_plan_slug,  # type: ignore[arg-type]
        status="pending",
        # delivery_status defaults to "manual" (Literal-frozen)
        message=UPGRADE_REQUEST_MESSAGE,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------
#  Usage events
# ---------------------------------------------------------------------


async def record_usage(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kind: UsageKind,
    quantity: int = 1,
    user_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> UsageEvent:
    """Single write path for usage. Future emitting services (CSV
    ingest, AI engine, etc.) call this function — never INSERT directly.

    `quantity` must be > 0 (DB CHECK enforces); `kind` must be in the
    canonical 5 (Pydantic Literal enforces at the call site).
    """
    if quantity <= 0:
        # Defense in depth — Pydantic would catch this, but service
        # callers may bypass schemas.
        raise ValueError(f"quantity must be > 0, got {quantity}")

    row = UsageEvent(
        organization_id=organization_id,
        user_id=user_id,
        brand_id=brand_id,
        kind=kind,
        quantity=quantity,
        event_metadata=metadata or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


async def get_usage_summary(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> UsageSummary:
    """Aggregate usage by `kind` for the org's current period.

    Phase 10.2e: every org is on Early Access (no period) so the
    summary returns all-time counts. When paid plans land, this will
    bound the WHERE clause by `subscription.period_start/end`.
    """
    sub = await ensure_subscription(
        session, organization_id=organization_id
    )

    # SUM(quantity) GROUP BY kind. We iterate the canonical kind list
    # to materialise zero-count cells (cleaner UI than missing rows).
    stmt = (
        select(UsageEvent.kind, func.sum(UsageEvent.quantity))
        .where(UsageEvent.organization_id == organization_id)
    )
    if sub.period_start is not None:
        stmt = stmt.where(UsageEvent.occurred_at >= sub.period_start)
    if sub.period_end is not None:
        stmt = stmt.where(UsageEvent.occurred_at < sub.period_end)
    stmt = stmt.group_by(UsageEvent.kind)

    rows = (await session.execute(stmt)).all()
    used_by_kind: dict[str, int] = {k: int(s or 0) for k, s in rows}

    cells: list[UsageBreakdownCell] = []
    for kind in plan_catalog.all_usage_kinds():
        used = used_by_kind.get(kind, 0)
        limit = plan_catalog.quota_for(sub.plan_slug, kind)
        percent = (
            None
            if limit is None or limit == 0
            else min(100.0, round((used / limit) * 100.0, 2))
        )
        cells.append(
            UsageBreakdownCell(
                kind=kind,
                display_name=plan_catalog.USAGE_DISPLAY_NAMES[kind],
                used=used,
                limit=limit,
                percent_used=percent,
            )
        )

    return UsageSummary(
        organization_id=organization_id,
        plan_slug=sub.plan_slug,  # type: ignore[arg-type]
        period_start=sub.period_start,
        period_end=sub.period_end,
        cells=cells,
    )


# ---------------------------------------------------------------------
#  Invoices
# ---------------------------------------------------------------------


async def list_invoices(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    limit: int = 50,
) -> InvoiceList:
    """List invoices for the org, newest first.

    Empty for Early Access — the UI should render an empty state like
    "No invoices yet — you're on Early Access" rather than spinning."""
    stmt = (
        select(Invoice)
        .where(Invoice.organization_id == organization_id)
        .order_by(desc(Invoice.period_end))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return InvoiceList(invoices=[_to_invoice_read(r) for r in rows])


# ---------------------------------------------------------------------
#  Pure projections
# ---------------------------------------------------------------------


def _to_subscription_read(sub: Subscription) -> SubscriptionRead:
    descriptor = plan_catalog.descriptor_for(sub.plan_slug)
    plan_display = (
        descriptor.display_name if descriptor else sub.plan_slug
    )
    return SubscriptionRead(
        id=sub.id,
        organization_id=sub.organization_id,
        plan_slug=sub.plan_slug,  # type: ignore[arg-type]
        plan_display_name=plan_display,
        status=sub.status,  # type: ignore[arg-type]
        period_start=sub.period_start,
        period_end=sub.period_end,
        trial_ends_at=sub.trial_ends_at,
        canceled_at=sub.canceled_at,
        cancel_at_period_end=sub.cancel_at_period_end,
        is_on_default_plan=(
            sub.plan_slug == plan_catalog.default_plan_slug()
        ),
        # "Paid plan" = anything that isn't the default. Stays true
        # when Growth/Scale ship.
        is_paid_plan=(sub.plan_slug != plan_catalog.default_plan_slug()),
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def _to_invoice_read(inv: Invoice) -> InvoiceRead:
    return InvoiceRead(
        id=inv.id,
        number=inv.number,
        status=inv.status,  # type: ignore[arg-type]
        amount_total_cents=inv.amount_total_cents,
        currency=inv.currency,
        period_start=inv.period_start,
        period_end=inv.period_end,
        due_at=inv.due_at,
        paid_at=inv.paid_at,
        hosted_invoice_url=inv.hosted_invoice_url,
        created_at=inv.created_at,
    )
