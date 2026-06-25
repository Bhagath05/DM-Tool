"""Phase 10.2f — Org router shape.

Pins:
  - new /orgs/{id}/profile (GET, PATCH) and /orgs/{id}/analytics (GET)
    appear under /api/v1
  - prior W1 routes still exist (regression guard)
"""

from __future__ import annotations

from aicmo.main import app


def _orgs_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        path = str(getattr(r, "path", ""))
        if not path.startswith("/api/v1/orgs"):
            continue
        for m in r.methods or set():
            out.add((path, m))
    return out


def test_profile_routes_registered() -> None:
    paths = _orgs_routes()
    expected = {
        ("/api/v1/orgs/{org_id}/profile", "GET"),
        ("/api/v1/orgs/{org_id}/profile", "PATCH"),
        ("/api/v1/orgs/{org_id}/analytics", "GET"),
    }
    missing = expected - paths
    assert not missing, f"Phase 10.2f routes missing: {missing}"


def test_prior_w1_routes_still_present() -> None:
    """Regression guard — adding the profile routes shouldn't have
    knocked out the W1 CRUD or member endpoints."""
    paths = _orgs_routes()
    expected = {
        ("/api/v1/orgs", "GET"),
        ("/api/v1/orgs", "POST"),
        ("/api/v1/orgs/workspace", "POST"),
        ("/api/v1/orgs/{org_id}", "GET"),
        ("/api/v1/orgs/{org_id}", "PATCH"),
        ("/api/v1/orgs/{org_id}", "DELETE"),
        ("/api/v1/orgs/{org_id}/members", "GET"),
    }
    missing = expected - paths
    assert not missing, f"W1 routes regressed: {missing}"
