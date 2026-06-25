# Phase 0 + Phase 1 — Completion Report

> Built back-to-back per approval. Reuse-first, PostgreSQL system of
> record, tenant isolation + RLS readiness preserved, backward compatible.
> Date: 2026-06-11.

---

## Phase 0 — ARQ Tenant-Context Propagation (foundation)

The job system was scaffolded but **had zero jobs and zero enqueue
callers**, so this built the tenant-carrying harness once — the safety
precondition for every future autonomous/scheduled feature.

**Files**
- `aicmo/queue/enqueue.py` — `TenantEnvelope` (server-authored) + `enqueue_tenant_job`.
- `aicmo/queue/context.py` — `@tenant_job` decorator (restores structlog + Sentry + RLS GUC, opens a dedicated session, clears tags on exit).
- `aicmo/queue/reference.py` — reference job (test template).
- `aicmo/queue/deps.py` — `get_arq_pool` FastAPI dependency.
- `aicmo/queue/worker.py` — `ALL_JOBS` registry.
- `aicmo/main.py` — lifespan opens an optional ARQ pool (guarded — API boots without Redis).
- `aicmo/config.py` — `jobs_enabled` kill switch (default true).
- `tests/queue/test_job_harness.py` — 8 tests.

**Evidence:** 8/8 pass, incl. the live-DB proof that a job's session
carries the envelope's org in `app.current_org_id`, and context cleared
on success AND error.

**Rollback:** nothing depends on jobs; stop the worker / revert `queue/*` / `JOBS_ENABLED=false`. No DB change.

---

## Phase 1 — Stripe Billing + DB-Configurable Usage Metering

### Technical design (as built)
- **Two dark-launch flags** (`billing_live_enabled`, `billing_enforce_limits`), both default **false** → the whole phase ships dormant; current behavior unchanged.
- **DB is the source of truth for plans + limits** (`plan`, `plan_quota` tables) — tunable with SQL, no deploy. Stripe price ids live in `plan.stripe_price_id`.
- **`subscription.plan_slug` CHECK → FK to `plan.slug`** — adding a plan is an INSERT, no migration.
- **Stripe gateway** (`payments/stripe_gateway.py`) — lazy SDK import (app/tests run without `stripe`); Checkout + Billing Portal are Stripe-hosted (**no card data in our DB**, PCI SAQ-A).
- **3 endpoints**: `POST /billing/checkout`, `POST /billing/portal` (owner-gated), `POST /billing/webhooks/stripe` (public, signature-verified, idempotent).
- **Metering**: `record_metered` (emit) wired into ads/content/visuals/campaigns generation + lead capture; `enforce_quota` (soft pre-check) in the 4 generation services. Bundles deliberately **not** metered (its sub-generators self-meter — avoids double-count). Lead capture is metered but **never gated** (never reject an inbound visitor).

### Database impact — migration `0033_billing_live` (applied + verified)
- New `plan` (5 rows seeded), `plan_quota` (9 rows), `stripe_event` (idempotency log).
- `usage_event.kind` CHECK extended with `generation`, `campaign`, `lead`.
- `subscription` / `billing_upgrade_request` plan CHECKs → FKs to `plan`.
- `subscription` / `invoice` data **untouched** (external-ID columns already existed).
- Seeded limits (your placeholder numbers, all DB-tunable):

| Plan | generation/mo | campaign/mo | lead/mo |
|---|---|---|---|
| early_access | ∞ | ∞ | ∞ |
| free | 100 | 10 | 25 |
| starter | 2,000 | 100 | 500 |
| growth | 15,000 | 500 | 5,000 |
| scale | ∞ | ∞ | ∞ |

### APIs affected
- billing router: **+3 endpoints**; existing 5 unchanged.
- generation endpoints: gain a soft pre-check (returns the asset as before; would 402 only when enforcement is ON and over-limit). Early Access unlimited → no change for current users.

### Security impact
- **Webhook signature verification mandatory** (unverified → 400, dropped); idempotency via `stripe_event` (replay-safe).
- **No card data stored** (Stripe-hosted).
- `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` added to `SECRETS.md` + the **prod boot guard requires them only when `billing_live_enabled=true`** (verified: refuses boot when live+missing; boots fine when billing off).
- checkout/portal gated to `billing.manage` (Owner). Webhook is public but signature-gated. `usage_event` tenant-scoped + RLS-ready. gitleaks already covers `sk_live_`/`whsec_`.

### Rollback plan (ladder)
1. `billing_live_enabled=false` (default) → checkout/portal revert to the existing placeholder flow.
2. `billing_enforce_limits=false` (default) → usage recorded, never blocks.
3. Webhook issue → flip the live flag off; subscription rows untouched.
4. `alembic downgrade 0032` → reverses 0033 (verified live: tables dropped, original CHECKs restored, re-upgrade re-seeds).

### Success metrics
First conversion / MRR / checkout completion; 100% webhooks verified; 0 duplicate rows on replay; usage recorded per generation; 0 false blocks for Early Access; 0 generation 500s from the gate (fails open).

---

## Verification evidence

| Gate | Result |
|---|---|
| Migration 0033 applied | ✅ rev `0033_billing_live`; 5 plans + 9 quotas seeded; FK/CHECK swapped |
| Migration reversibility (live) | ✅ down→0032 (tables dropped, CHECK restored) → up→0033 (re-seeded) |
| Billing suite | ✅ 46 passed (incl. 8 new: quota soft/fail-open, DB-quota-change-without-code, webhook idempotency, unhandled-type ack, checkout flag-gate) |
| Phase 0 job harness | ✅ 8 passed (incl. live RLS-GUC-in-job proof) |
| Full backend suite | ✅ **915 passed**, 0 regressions |
| Boot guard | ✅ refuses prod boot when billing live + Stripe keys missing; boots when billing off |
| App import / route wiring | ✅ all 8 billing routes registered; no circular imports |

---

## Known follow-ups (not blocking; documented honestly)

1. **`/billing/usage` display still shows the legacy 5 kinds**, not the new `generation/campaign/lead` metrics. The new kinds ARE recorded + enforced; surfacing them on the usage page is a frontend+`get_usage_summary` change deferred to the billing-UI pass.
2. **Frontend checkout wiring** — the UI still uses the placeholder upgrade-request flow; wiring the "Upgrade" button to `POST /billing/checkout` (redirect to Stripe) is the frontend half, deferred. Backend returns 409 until then, so the existing UI keeps working.
3. **Enabling enforcement** later: flip `billing_enforce_limits=true` — the gate is already wired in all 4 generation services.
4. **Set real Stripe price ids** in `plan.stripe_price_id` (currently NULL) before going live.

---

## Constraint adherence
✅ PostgreSQL system of record (plans/quotas/usage all in PG) · ✅ no MongoDB · ✅ reuse-first (existing subscription/invoice/usage_event tables + record_usage + webhook pattern + boot guard) · ✅ tenant isolation + RLS readiness preserved (usage_event TenantMixin; jobs carry RLS GUC) · ✅ no card data · ✅ Stripe-hosted only · ✅ webhooks verified + idempotent + replay-safe · ✅ backward compatible (dark-launch flags, additive migration) · ✅ migration verification + rollback validation + test evidence provided.
