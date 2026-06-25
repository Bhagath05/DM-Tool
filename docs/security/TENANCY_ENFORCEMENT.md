# Tenancy Enforcement — Decision Record (P1)

**Status:** Decided · **Date:** 2026-06-24 · **Supersedes:** CLAUDE.md A5
"known limitation #2" (no middleware-level tenant assertion)

---

## The decision

DM Tool enforces tenant isolation at the **application layer** and keeps
PostgreSQL Row-Level Security **dormant** as staged defence-in-depth.

This is now a *formal, tested* posture rather than an implicit one. Two
things make it real:

1. **A CI guard** — `apps/api/tests/tenancy/test_route_tenant_guard.py` — that
   walks every route the app mounts under `/api/v1`, inspects its actual
   FastAPI dependency tree, and **fails the build** if any route is neither
   tenant-guarded nor on an explicit, justified allowlist.
2. **This document**, which records *why* app-layer is the enforcement plane
   for launch, and the exact, reviewed exceptions.

## Why app-layer, not database RLS (for launch)

The RLS machinery already exists and is correct (migration `0032`, 19
policies, GUC plumbing in the resolver, activation/deactivation scripts, and
isolation tests — see `docs/database/RLS_ACTIVATION.md`). It is **off by
default** (`DB_RLS_ENABLED=false`, confirmed: 0 tables with `rowsecurity`).

We are **not** activating it as part of launch hardening, for these reasons:

| Factor | App-layer (chosen) | Activate RLS now (deferred) |
|---|---|---|
| Blast radius | None — already the live path on every request | Every query in every module runs under new policies; a single mis-scoped policy = data outage |
| Verifiability | One CI test pins all ~N routes deterministically | Needs a Postgres-backed integration suite that CI does not yet have |
| Failure mode | A forgotten guard → caught by CI before merge | A wrong policy → silent empty result sets or cross-tenant leak at runtime |
| Reversibility | N/A | Reversible, but mid-incident toggling under load is risky |

App-layer is where 100% of enforcement already happens. The honest,
lower-risk hardening is to make that plane **provably complete**, not to flip
on a second plane whose test infrastructure isn't in CI yet. RLS stays
staged: when a Postgres-backed integration suite lands, activation becomes a
flag flip with the existing scripts — no new code.

## What "app-layer enforced" means concretely

Every protected route declares a dependency that resolves a frozen
`TenantContext` before the handler body runs:

- `Depends(require_tenant())` / `require_tenant(brand_optional=True)`, or
- `Depends(require_permission("<slug>"))` (which composes `require_tenant`).

`require_tenant` (in `aicmo/tenancy/dependencies.py`) re-validates membership,
org status, brand-in-org, and brand status **on every request** against the
database — the client headers are assumed adversarial. Services filter by the
resolved `brand_id` / `organization_id`, never by a client-supplied id. The
full trust-boundary analysis is in CLAUDE.md ("End-to-end tenant lifecycle").

## The allowlist (the only routes without a tenant context)

The CI guard classifies each `/api/v1` route as `tenant`, `user`, or `public`
by inspecting its dependency tree. Anything not `tenant` must be on one of two
allowlists, each entry a deliberate choice:

### PUBLIC — no Authorization (authenticated by their own mechanism)

| Prefix / path | Authenticated by | Why it can't carry a tenant |
|---|---|---|
| `/api/v1/webhooks/clerk` | Svix HMAC signature | Clerk is the caller; no user session |
| `/api/v1/billing/webhooks/stripe` | Stripe signature | Stripe is the caller |
| `/api/v1/integrations/oauth/callback` | OAuth `state` param | Provider redirect, mid-handshake |
| `/api/v1/social/oauth/{platform}/callback` | OAuth `state` param | Provider redirect (sibling `/init` IS tenant-guarded) |
| `/api/v1/media/**` | Signed URL | Public asset serving; the signature is the grant |
| `/api/v1/poster/media` | Expiring signed URL | Public LinkedIn-poster PNG serving |
| `/api/v1/public/landing-pages/**` | Public by design | Anonymous visitors view/submit |
| `/api/v1/public/leads/**` | Public by design | Anonymous lead-capture submission |
| `/api/v1/invites/{token}` (GET) | Single-use invite token | Recipient has no membership *yet* |
| `/api/v1/social/availability` | n/a (no data) | Env-level capability probe; no session, no tenant rows |
| `/api/v1/debug/**` | n/a | **Dev/staging ONLY** — not mounted when `api_env==production` (`aicmo/main.py`) |

### AUTH-ONLY — authenticated, intentionally pre-tenant (bootstrap surface)

| Path | Why no tenant |
|---|---|
| `/api/v1/users/me` | Returns the user's memberships; must not 4xx when they have none |
| `/api/v1/orgs` (POST create, GET list) | Creating/listing the user's first org — there is no tenant yet |
| `/api/v1/orgs/workspace` | Onboarding's single transactional org+brand create |
| `/api/v1/rbac/**` (catalog) | Global role/permission reference data, identical for all tenants |
| `/api/v1/invites/accept` (POST) | Accepting an invite to join an org you are not yet a member of |

Every other `/api/v1` route **must** resolve a `TenantContext`, enforced by CI.

### Census (verified 2026-06-24 against the mounted app)

`204` routes under `/api/v1`: **183 tenant-guarded**, **7 auth-only**, **14 public**
— every non-tenant route accounted for by an allowlist entry above. The guard
also self-checks the allowlist: a PUBLIC entry that secretly resolves a tenant
fails `test_allowlisted_public_routes_are_genuinely_unauthenticated` (this
caught an over-broad `/social/oauth/` prefix during authoring — narrowed to the
exact `/callback`).

## How a future change is governed

- Add a tenant-scoped route → just use `Depends(require_tenant/…)`. CI is green.
- Add a route and forget the guard → CI fails with the offending path until
  you either guard it or consciously allowlist it here + in the test.
- Want database RLS too → follow `docs/database/RLS_ACTIVATION.md`; flip
  `DB_RLS_ENABLED=true` after the Postgres integration suite is in CI. App-layer
  enforcement remains regardless — the two planes are complementary.

## Tests

- `apps/api/tests/tenancy/test_route_tenant_guard.py`
  - `test_every_api_route_is_tenant_guarded_or_allowlisted` — the guard
  - `test_allowlisted_public_routes_are_genuinely_unauthenticated` — a public
    allowlist entry may not secretly require a tenant (would break webhooks)
  - `test_auth_only_allowlist_routes_are_authenticated` — an auth-only entry
    must actually require a user (else it's public / a bug)
- Run standalone for the full classification table:
  `python tests/tenancy/test_route_tenant_guard.py`
