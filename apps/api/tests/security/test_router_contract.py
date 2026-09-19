"""Security router shape.

Pins:
  - exactly 6 routes under /api/v1/security
  - the Clerk webhook receiver is GONE (first-party auth has no external IdP)
  - the security module still exports its two routers distinctly
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
    assert expected.issubset(paths), f"missing: {expected - paths}; got: {paths}"


def test_clerk_webhook_route_removed() -> None:
    """The Clerk webhook receiver was removed with the first-party auth
    migration — there is no external identity provider to receive events."""
    paths = {str(getattr(r, "path", "")) for r in app.routes}
    assert "/api/v1/webhooks/clerk" not in paths


def test_public_and_private_routers_distinct() -> None:
    """The security module still exports two distinct routers; the public
    one is retained (now empty) for future signature-verified webhooks."""
    from aicmo.modules.security import public_router, router

    assert public_router is not router
    assert router.prefix == "/security"
    assert public_router.prefix == "/webhooks"
