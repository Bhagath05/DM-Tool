"""Phase 10.2e + Phase 1 — Router contract.

Pins:
  - exactly the billing routes (5 original + 3 Phase-1: checkout, portal,
    webhook)
  - permission split preserved
  - no HTTP recorder endpoint (anti-inflation)
"""

from __future__ import annotations

from aicmo.main import app


def test_exactly_billing_routes() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if str(getattr(r, "path", "")).startswith("/api/v1/billing")
    }
    expected = {
        # Phase 10.2e
        ("/api/v1/billing/plans", "GET"),
        ("/api/v1/billing/subscription", "GET"),
        ("/api/v1/billing/usage", "GET"),
        ("/api/v1/billing/invoices", "GET"),
        ("/api/v1/billing/upgrade-request", "POST"),
        # Phase 1 — Stripe live billing
        ("/api/v1/billing/checkout", "POST"),
        ("/api/v1/billing/portal", "POST"),
        ("/api/v1/billing/webhooks/stripe", "POST"),
    }
    assert paths == expected, (
        f"unexpected billing routes; got: {paths}"
    )


def test_no_http_recorder_endpoint() -> None:
    """If a `/billing/usage/record` POST route appears, a logged-in
    user can inflate their own usage counters — billing-integrity bug.
    Future emitting services must call `billing_service.record_usage()`
    directly, never via HTTP."""
    paths = {str(getattr(r, "path", "")) for r in app.routes}
    forbidden = (
        "/api/v1/billing/usage/record",
        "/api/v1/billing/record-usage",
        "/api/v1/billing/events",
    )
    for p in forbidden:
        assert p not in paths, (
            f"HTTP usage recorder appeared at {p} — clients can inflate "
            "their own usage. Remove the route; emit via Python only."
        )


def test_no_stripe_webhook_route_yet() -> None:
    """Phase 10.2e ships WITHOUT Stripe. A `/webhooks/stripe` route
    would imply we're listening for events that won't arrive. Pin
    that the route is deliberately absent until the Stripe phase."""
    paths = {str(getattr(r, "path", "")) for r in app.routes}
    assert "/api/v1/webhooks/stripe" not in paths, (
        "Stripe webhook route appeared in Phase 10.2e — defer until "
        "real Stripe integration ships."
    )
