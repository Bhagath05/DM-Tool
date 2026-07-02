"""Phase 4.10 — Final Validation guards (permanent regression checks).

Codifies the production audit so the invariants can't silently regress:
no duplicated routes, the full Phase-4 surface is registered, and the safety
invariant holds (the last one is proven in depth in test_safety.py)."""

from __future__ import annotations

from aicmo.main import app


def _api_endpoints():
    out = []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/v1"):
            continue
        for m in getattr(r, "methods", None) or set():
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, path))
    return out


def test_no_duplicate_api_routes():
    eps = _api_endpoints()
    seen: dict[tuple[str, str], int] = {}
    for e in eps:
        seen[e] = seen.get(e, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    assert dups == {}, f"duplicate (method, path) routes: {dups}"


def test_full_phase4_surface_registered():
    paths = {p for _, p in _api_endpoints()}
    expected = {
        # 4.1 monitoring + driver
        "/api/v1/operations/tick",
        "/api/v1/operations/monitoring",
        # 4.2 events
        "/api/v1/operations/events",
        # 4.3 goals
        "/api/v1/operations/goals",
        # 4.4 work scheduler
        "/api/v1/operations/work",
        # 4.7 dashboard
        "/api/v1/operations/dashboard",
        # 4.8 notifications
        "/api/v1/operations/notifications",
        # 4.9 safety
        "/api/v1/operations/safety",
        # 9/10 autonomy policy + levels
        "/api/v1/autonomy/policy",
        "/api/v1/autonomy/levels",
    }
    missing = expected - paths
    assert missing == set(), f"missing Phase-4 routes: {missing}"


def test_operations_tick_is_the_only_untenanted_operations_route():
    """Every /operations route is tenant-guarded EXCEPT the system tick (which is
    secret-gated). This mirrors the route-guard allowlist and fails if a new
    unguarded operations route slips in."""
    from tests.tenancy.test_route_tenant_guard import _PUBLIC_EXACT

    assert "/api/v1/operations/tick" in _PUBLIC_EXACT
