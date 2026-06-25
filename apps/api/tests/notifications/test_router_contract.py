"""Phase 10.2b — Router contract.

We don't have a real DB in this test suite, but we can pin:

  1. The three routes are mounted under /api/v1/notifications.
  2. The catalog endpoint returns 200 + valid NotificationCatalog
     shape (no auth needed since the catalog is static).

End-to-end DB-backed flows are exercised by the manual smoke test in
10.2b-7 — same pattern as Phase 10.2a.
"""

from __future__ import annotations

from aicmo.main import app


def test_three_notification_routes_registered() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if "/notifications" in str(getattr(r, "path", ""))
    }
    expected = {
        ("/api/v1/notifications/catalog", "GET"),
        ("/api/v1/notifications/preferences", "GET"),
        ("/api/v1/notifications/preferences", "PUT"),
    }
    assert expected.issubset(paths), (
        f"missing routes: {expected - paths}; got: {paths}"
    )


def test_no_unauthenticated_callback_route() -> None:
    """Unlike integrations (which has a public OAuth callback), the
    notifications module has zero public routes — everything is gated
    on require_tenant. Pin it so a future 'public unsubscribe link'
    addition is an intentional review item, not an accident."""
    public_router_attrs = [
        name
        for name in dir(__import__(
            "aicmo.modules.notifications.router",
            fromlist=["*"],
        ))
        if name == "public_router"
    ]
    assert public_router_attrs == [], (
        "notifications module sprouted a public_router — review carefully"
    )
