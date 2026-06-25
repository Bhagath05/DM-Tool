"""Phase 10.2f — Brand router shape.

Pin the new endpoints under /api/v1/brands/{id}:
    - GET    /profile
    - PATCH  /profile
    - POST   /default
    - POST   /activate

Plus regression guard: the pre-10.2f routes still exist.
"""

from __future__ import annotations

from aicmo.main import app


def _brand_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        path = str(getattr(r, "path", ""))
        if not path.startswith("/api/v1/brands"):
            continue
        for m in r.methods or set():
            out.add((path, m))
    return out


def test_profile_default_activate_routes_registered() -> None:
    paths = _brand_routes()
    expected = {
        ("/api/v1/brands/{brand_id}/profile", "GET"),
        ("/api/v1/brands/{brand_id}/profile", "PATCH"),
        ("/api/v1/brands/{brand_id}/default", "POST"),
        ("/api/v1/brands/{brand_id}/activate", "POST"),
    }
    missing = expected - paths
    assert not missing, f"Phase 10.2f brand routes missing: {missing}"


def test_prior_w1_brand_routes_still_present() -> None:
    paths = _brand_routes()
    expected = {
        ("/api/v1/brands/{brand_id}", "GET"),
        ("/api/v1/brands/{brand_id}", "PATCH"),
        ("/api/v1/brands/{brand_id}", "DELETE"),
    }
    missing = expected - paths
    assert not missing, f"W1 brand routes regressed: {missing}"


def test_no_default_clear_endpoint() -> None:
    """We don't ship a 'clear org default' endpoint. The default
    transfers atomically via POST /brands/{id}/default. If we add a
    DELETE later it should be intentional — pin the absence."""
    paths = {p for p, _m in _brand_routes()}
    assert "/api/v1/brands/{brand_id}/default" in paths
    # No DELETE on the same path
    methods = {
        m
        for p, m in _brand_routes()
        if p == "/api/v1/brands/{brand_id}/default"
    }
    assert "DELETE" not in methods, (
        "Unexpected DELETE on /brands/{id}/default — clearing the org "
        "default isn't a designed flow; promote a different brand instead."
    )
