"""P1 hardening — RLS decision CI guard: app-layer tenancy is enforced.

This is the teeth behind the architectural decision recorded in
`docs/security/TENANCY_ENFORCEMENT.md`: DM Tool enforces tenant isolation at
the **application layer** (every protected route resolves a `TenantContext`
via `require_tenant` / `require_permission`), with database RLS kept dormant
as defence-in-depth (flag `DB_RLS_ENABLED=false`).

The historical risk (CLAUDE.md A5 "known limitation #2") was: *a new route
that forgets `Depends(require_tenant)` is authenticated but unscoped.* This
test closes that gap. It walks every route the app actually mounts under
`/api/v1`, classifies each by inspecting its real FastAPI dependency tree,
and fails CI if a route is neither tenant-guarded nor on one of two explicit,
documented allowlists:

  * **PUBLIC**  — no auth at all (webhooks verified by signature, OAuth
    callbacks, signed-URL media, public landing pages / lead capture, invite
    accept-by-token). These live under dedicated public prefixes.
  * **AUTH-ONLY** — authenticated but intentionally pre-tenant (the tenancy
    *bootstrap* surface: `/me`, org create/list, onboarding workspace, and
    the global RBAC catalog). A user has no tenant yet when calling these.

Adding a new business route without a tenant dependency now breaks the build
until the author either guards it or consciously adds it to an allowlist with
a justification. That is the whole point.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from aicmo.auth.clerk import require_user
from aicmo.main import app

# --- intentional exceptions (every entry is a deliberate, reviewed choice) ---

# Fully public namespaces — no Authorization required. Each is safe because
# its own mechanism authenticates the caller (HMAC signature, OAuth state,
# signed URL, or a single-use invite token), not a tenant session.
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/v1/public/",              # public landing pages + public lead capture
    "/api/v1/webhooks/",           # Clerk webhook (Svix signature-verified)
    "/api/v1/media/",              # signed-URL media serving (visuals + creative)
    "/api/v1/invites/",            # invite view/accept by token (pre-membership)
    "/api/v1/integrations/oauth/", # OAuth provider redirect callbacks (state-verified)
    "/api/v1/debug/",              # observability diagnostics — dev/staging ONLY; the
                                   # debug router is not mounted when api_env==production
                                   # (aicmo/main.py), so these never exist in prod.
)
_PUBLIC_EXACT: frozenset[str] = frozenset(
    {
        "/api/v1/billing/webhooks/stripe",  # Stripe webhook (signature-verified)
        "/api/v1/poster/media",             # public expiring signed-PNG serving
        "/api/v1/social/availability",      # capability probe — no session, no tenant data
        # social OAuth *callback* only — the sibling /oauth/{platform}/init is
        # tenant-guarded (a logged-in user starting the connect flow), so we must
        # NOT use a broad /social/oauth/ prefix here.
        "/api/v1/social/oauth/{platform}/callback",  # state-verified provider redirect
        # Phase 4 continuous-loop driver. A SYSTEM endpoint that runs across ALL
        # tenants (iterates active brands RLS-bypassed), so it is deliberately
        # NOT tenant-scoped. Secured instead by a shared operations secret
        # (X-Operations-Token) + global throttle; disabled (503) until a secret
        # is configured. The sibling /operations/monitoring IS tenant-guarded.
        "/api/v1/operations/tick",
    }
)

# Authenticated but intentionally pre-tenant — the tenancy bootstrap surface.
# A freshly-signed-in user with zero memberships must be able to reach these.
_AUTH_ONLY_EXACT: frozenset[str] = frozenset(
    {
        "/api/v1/users/me",
        "/api/v1/orgs",            # POST create + GET list (pre-tenant)
        "/api/v1/orgs/workspace",  # onboarding: single transactional create
        # Global storage capability — config-derived booleans only (media
        # backend + whether durable object storage is configured). No tenant
        # data; identical for every tenant, so tenant-scoping it would be
        # wrong. Auth-required; the admin-gating of the UI notice is client-side.
        "/api/v1/system/storage",
    }
)
_AUTH_ONLY_PREFIXES: tuple[str, ...] = (
    "/api/v1/rbac/",      # global RBAC catalog (reference data, not tenant-scoped)
    "/api/v1/invites/",   # invite *accept* is authed but pre-tenant (joining a new org)
    "/api/v1/debug/",     # dev/staging-only; sentry-authed is authed but tenant-less
)


# --------------------------------------------------------------------------
#  Dependency-tree classification
# --------------------------------------------------------------------------


def _iter_calls(dependant) -> list:
    """Flatten a FastAPI Dependant tree into the list of its `.call` objects."""
    calls = []
    stack = list(getattr(dependant, "dependencies", []))
    while stack:
        d = stack.pop()
        if getattr(d, "call", None) is not None:
            calls.append(d.call)
        stack.extend(getattr(d, "dependencies", []))
    return calls


def _is_tenant_call(call) -> bool:
    # require_tenant() and require_permission() both return an inner closure
    # named `_dep`; their __qualname__ carries the factory name. This is the
    # stable signal that a TenantContext is resolved for the request.
    qn = getattr(call, "__qualname__", "") or ""
    return "require_tenant." in qn or "require_permission." in qn


def _is_user_call(call) -> bool:
    if call is require_user:
        return True
    return (getattr(call, "__qualname__", "") or "") == "require_user"


def classify(route: APIRoute) -> str:
    """Return 'tenant' | 'user' | 'public' for a mounted route."""
    calls = _iter_calls(route.dependant)
    if any(_is_tenant_call(c) for c in calls):
        return "tenant"
    if any(_is_user_call(c) for c in calls):
        return "user"
    return "public"


def _api_routes() -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and str(r.path).startswith("/api/v1")
    ]


def _on_public_allowlist(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)


def _on_auth_only_allowlist(path: str) -> bool:
    return path in _AUTH_ONLY_EXACT or path.startswith(_AUTH_ONLY_PREFIXES)


# --------------------------------------------------------------------------
#  The guard
# --------------------------------------------------------------------------


def test_every_api_route_is_tenant_guarded_or_allowlisted() -> None:
    """No /api/v1 route may be unscoped unless it is on an explicit allowlist."""
    offenders: list[str] = []
    for r in _api_routes():
        kind = classify(r)
        if kind == "tenant":
            continue
        if kind == "user" and _on_auth_only_allowlist(r.path):
            continue
        if kind == "public" and _on_public_allowlist(r.path):
            continue
        methods = ",".join(sorted(r.methods or []))
        offenders.append(f"{kind:7s} {methods:18s} {r.path}")

    assert not offenders, (
        "Routes under /api/v1 that are neither tenant-guarded nor allowlisted "
        "(add Depends(require_tenant/require_permission), or — if intentionally "
        "public/pre-tenant — add to the allowlist in this file with a reason):\n"
        + "\n".join(sorted(offenders))
    )


def test_allowlisted_public_routes_are_genuinely_unauthenticated() -> None:
    """A path on the PUBLIC allowlist must NOT carry a tenant dependency — if
    it did, the allowlist entry would be a lie and the route would 4xx its
    legitimate unauthenticated callers (webhooks, OAuth callbacks)."""
    for r in _api_routes():
        if _on_public_allowlist(r.path) and not _on_auth_only_allowlist(r.path):
            assert classify(r) != "tenant", (
                f"{r.path} is PUBLIC-allowlisted but resolves a TenantContext — "
                "remove it from the allowlist or drop the tenant dependency."
            )


def test_auth_only_allowlist_routes_are_authenticated() -> None:
    """An AUTH-ONLY allowlist entry must actually require a user — otherwise
    it's fully public and belongs on the public allowlist (or is a bug)."""
    auth_only = [
        r
        for r in _api_routes()
        if _on_auth_only_allowlist(r.path) and not _on_public_allowlist(r.path)
    ]
    assert auth_only, "expected the bootstrap routes to be mounted"
    for r in auth_only:
        assert classify(r) in {"user", "tenant"}, (
            f"{r.path} is AUTH-ONLY allowlisted but requires no authentication."
        )


if __name__ == "__main__":
    # Standalone discovery/evidence mode: print the full classification table.
    rows = sorted(
        (classify(r), ",".join(sorted(r.methods or [])), r.path)
        for r in _api_routes()
    )
    counts = {"tenant": 0, "user": 0, "public": 0}
    for kind, methods, path in rows:
        counts[kind] += 1
        flag = ""
        if kind == "user" and not _on_auth_only_allowlist(path):
            flag = "  <-- UNGUARDED (user, not allowlisted)"
        if kind == "public" and not _on_public_allowlist(path):
            flag = "  <-- UNGUARDED (public, not allowlisted)"
        print(f"{kind:7s} {methods:20s} {path}{flag}")
    print(
        f"\nTOTAL {sum(counts.values())} api routes — "
        f"tenant={counts['tenant']} user={counts['user']} public={counts['public']}"
    )
