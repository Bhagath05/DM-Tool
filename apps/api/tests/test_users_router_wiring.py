"""Sanity tests for the /api/v1/me endpoint wiring.

We don't spin up Postgres in this suite (no async-pg test harness yet).
Instead these tests assert the route is registered with the expected
shape — enough to catch wire-up regressions during the A3 frontend work.

Full integration coverage needs a Postgres test fixture, which is
tracked separately under the testing-infra backlog.
"""

from __future__ import annotations

from aicmo.main import app


def test_me_route_is_registered() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/v1/users/me" in paths


def test_me_route_is_get_only() -> None:
    me_routes = [
        r for r in app.routes if getattr(r, "path", "") == "/api/v1/users/me"
    ]
    assert len(me_routes) == 1
    methods = me_routes[0].methods  # type: ignore[attr-defined]
    assert methods == {"GET"}


def test_orgs_router_mounted_under_v1() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert any(p.startswith("/api/v1/orgs") for p in paths)


def test_brands_router_mounted_under_v1() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert any(p.startswith("/api/v1/brands") for p in paths)


def test_rbac_router_mounted_under_v1() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert any(p.startswith("/api/v1/rbac") for p in paths)
