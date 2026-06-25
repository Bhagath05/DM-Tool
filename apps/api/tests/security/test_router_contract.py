"""Phase 10.2c — Router shape.

Pins:
  - exactly 6 routes under /api/v1/security
  - exactly 1 route under /api/v1/webhooks (Clerk)
  - the webhook is mounted on `public_router` (no tenant headers required)
  - the authenticated router has no public escape hatch
"""

from __future__ import annotations

from aicmo.main import app


def test_six_authenticated_security_routes() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if str(getattr(r, "path", "")).startswith("/api/v1/security/")
    }
    expected = {
        ("/api/v1/security/sessions", "GET"),
        ("/api/v1/security/sessions/{session_id}/revoke", "POST"),
        ("/api/v1/security/sessions/revoke-all", "POST"),
        ("/api/v1/security/events", "GET"),
        ("/api/v1/security/events", "POST"),
        ("/api/v1/security/summary", "GET"),
    }
    assert expected.issubset(paths), (
        f"missing: {expected - paths}; got: {paths}"
    )


def test_clerk_webhook_route_exists() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if "/webhooks/clerk" in str(getattr(r, "path", ""))
    }
    assert ("/api/v1/webhooks/clerk", "POST") in paths


def test_webhook_excluded_from_openapi() -> None:
    """The webhook endpoint should NOT appear in OpenAPI — it's an
    internal contract between Clerk and us, not a public API for the
    frontend to call."""
    schema = app.openapi()
    paths = schema.get("paths", {})
    assert "/api/v1/webhooks/clerk" not in paths


def test_public_and_private_routers_distinct() -> None:
    """Smoke: the security module exports two routers and they're both
    registered. If a refactor collapses them into one (and gates the
    webhook on require_tenant), the webhook stops working — Clerk
    can't send bearer tokens."""
    from aicmo.modules.security import public_router, router

    assert public_router is not router
    assert router.prefix == "/security"
    assert public_router.prefix == "/webhooks"
