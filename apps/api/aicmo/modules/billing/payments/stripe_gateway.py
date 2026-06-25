"""Stripe gateway — Phase 1.

A thin, stubbable wrapper over the `stripe` SDK. The SDK is imported
LAZILY inside each function so the app + the test suite run without
`stripe` installed (the live path is flag-gated and dark by default).
Tests monkeypatch these module-level functions; only production with
`billing_live_enabled=true` exercises the real SDK.

No card data ever passes through here — we use Stripe-hosted Checkout +
Billing Portal, so PCI scope stays at SAQ-A. We only ever handle opaque
customer / subscription / price ids + the signed webhook payload.
"""

from __future__ import annotations

import uuid
from typing import Any

from aicmo.config import get_settings


class StripeNotConfigured(RuntimeError):
    """Raised when a live Stripe call is attempted without the SDK or
    secret key. Surfaced to the caller as a clean 503, never a 500 stack."""


def _stripe() -> Any:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not set")
    try:
        import stripe  # lazy — keeps the dep optional for dev/tests
    except ImportError as e:  # pragma: no cover - only when SDK absent
        raise StripeNotConfigured("the `stripe` package is not installed") from e
    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_or_get_customer(
    *, organization_id: uuid.UUID, email: str | None, name: str | None,
    existing_customer_id: str | None = None,
) -> str:
    """Return a Stripe customer id, reusing an existing one when present."""
    if existing_customer_id:
        return existing_customer_id
    stripe = _stripe()
    customer = stripe.Customer.create(
        email=email or None,
        name=name or None,
        metadata={"organization_id": str(organization_id)},
    )
    return customer.id


def create_checkout_session(
    *,
    organization_id: uuid.UUID,
    plan_slug: str,
    price_id: str,
    customer_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe-hosted subscription Checkout Session; return its URL."""
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(organization_id),
        metadata={"organization_id": str(organization_id), "plan_slug": plan_slug},
        subscription_data={
            "metadata": {"organization_id": str(organization_id), "plan_slug": plan_slug}
        },
    )
    return session.url


def create_billing_portal_session(*, customer_id: str, return_url: str) -> str:
    """Create a Stripe Billing Portal session; return its URL."""
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=return_url
    )
    return session.url


def construct_event(payload: bytes, sig_header: str) -> dict:
    """Verify the webhook signature and return the parsed event.

    Raises on an invalid signature — the caller drops the request. This
    is the ONLY trust boundary for the public webhook.
    """
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET is not set")
    stripe = _stripe()
    # Raises stripe.error.SignatureVerificationError on tampering.
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return event  # type: ignore[return-value]
