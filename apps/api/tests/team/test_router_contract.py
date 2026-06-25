"""Phase 10.2d — Router shape.

Pins:
  - exactly 5 routes under /api/v1/team
  - exactly 2 routes under /api/v1/invites (preview + accept)
  - public_router is distinct from router (different auth requirements)
"""

from __future__ import annotations

from aicmo.main import app


def test_five_team_routes_registered() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if str(getattr(r, "path", "")).startswith("/api/v1/team")
    }
    expected = {
        ("/api/v1/team", "GET"),
        ("/api/v1/team/roles", "GET"),
        ("/api/v1/team/invites", "GET"),
        ("/api/v1/team/invites", "POST"),
        ("/api/v1/team/invites/{invite_id}/revoke", "POST"),
    }
    assert expected.issubset(paths), (
        f"missing: {expected - paths}; got: {paths}"
    )


def test_two_invite_acceptance_routes() -> None:
    paths = {
        (r.path, ",".join(sorted(r.methods or [])))
        for r in app.routes
        if str(getattr(r, "path", "")).startswith("/api/v1/invites/")
    }
    expected = {
        ("/api/v1/invites/{token}", "GET"),
        ("/api/v1/invites/accept", "POST"),
    }
    assert expected.issubset(paths)


def test_team_module_exports_two_routers() -> None:
    """A future refactor that collapses router + public_router into
    one would gate /invites/* on require_tenant — and the invitee
    can't pass tenant headers (they're not a member yet). Pin the
    separation."""
    from aicmo.modules.team import public_router, router

    assert public_router is not router
    assert router.prefix == "/team"
    assert public_router.prefix == "/invites"
