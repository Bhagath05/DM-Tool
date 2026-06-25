# Phase 0 — Tenant-Context Propagation for ARQ Workers

> Foundation for all autonomous/scheduled work (Phases 2–6).
> Design only. No code until approved.

---

## Why this is Phase 0

Today the ARQ system is **scaffolded but unused**: `queue/worker.py`
registers `functions: list = []` and **nothing in the codebase enqueues a
job**. CLAUDE.md (A5 known-limitation #3) flags that background jobs don't
inherit request tenant context. Rather than retrofit (there's nothing to
retrofit), Phase 0 builds the **tenant-carrying job harness once**, so
every future job (Autopilot, Coach, scheduling, ad-sync) is tenant-scoped
and RLS-correct from its first line. This is the safety precondition for
any autonomous action.

---

## 1. Technical design

### 1.1 The problem a job must solve
A request handler resolves tenant via `require_tenant` → binds structlog
contextvars + Sentry tags + (when enabled) RLS GUCs. A background job has
**no request**, so none of that happens. A job that queries `leads` would
either see nothing (RLS on) or — worse, RLS off — have no tenant scoping
at all and rely entirely on the caller passing `brand_id` correctly.

### 1.2 Approach — capture at enqueue, restore at execute
Three small pieces, all reusing existing primitives:

**(a) Enqueue side — `enqueue_tenant_job(...)`** (`aicmo/queue/enqueue.py`)
Wraps `arq` `enqueue_job`. Serializes an authoritative `_TenantEnvelope`
(org_id, brand_id, user_uuid, role_slugs) — built server-side from the
caller's `TenantContext`, **never from client input** — into the job
payload. Same trust model as the resolver.

**(b) Execute side — `@tenant_job` decorator** (`aicmo/queue/context.py`)
Wraps a job function. On entry it:
1. Pops the `_TenantEnvelope` from kwargs.
2. Opens a dedicated `AsyncSession` (jobs never share the request session).
3. `bind_contextvars(...)` + `bind_tenant_context(...)` — **reuse** the
   existing structlog + Sentry helpers (`observability/sentry.py`).
4. `rls.set_request_context(session, org, user)` — **reuse** the Phase-RLS
   helper, so jobs run under org-scoped RLS exactly like requests (no-op
   when `DB_RLS_ENABLED` is false).
5. Calls the wrapped function with `(ctx, session, tenant, *args)`.
6. On exit: commit/rollback + `clear_tenant_context()` so the worker's
   long-lived process never leaks tenant tags between jobs.

**(c) Pool wiring**
- FastAPI lifespan creates one `ArqRedis` pool (`app.state.arq`) and a
  `get_arq_pool()` dependency so handlers can enqueue.
- `WorkerSettings.functions` gains a registration helper; feature modules
  add jobs in `modules/<name>/tasks.py` (the convention already documented
  in CLAUDE.md) and register via a central `ALL_JOBS` list.

### 1.3 Reference job + test harness
Ship one trivial reference job (`queue/reference.py::echo_tenant_job`)
that selects `count(*) FROM leads` under the restored context — used only
by tests to prove isolation. No product behavior.

### 1.4 What is explicitly NOT in Phase 0
- No real feature jobs (those come with their phases).
- No cron schedules (Phase 2 adds the first via `cron_jobs`).
- No change to any request path — the resolver is untouched.

---

## 2. Database impact

**None.** No tables, no columns, no migration. Phase 0 is pure
application/runtime plumbing. Jobs reuse `SessionLocal`, existing tables,
and the existing RLS helpers.

---

## 3. APIs affected

**No external/public API changes.** Internal only:
- New module `aicmo/queue/{enqueue,context,reference}.py`.
- `main.py` lifespan: open/close the ARQ redis pool (additive; guarded so
  a missing Redis in a non-job context degrades gracefully).
- `WorkerSettings.functions` populated from `ALL_JOBS`.

No router, schema, or response-shape changes. OpenAPI is unchanged.

---

## 4. Security impact

**Net positive — this closes A5 limitation #3.**
- Background work becomes tenant-scoped: structlog + Sentry tags + RLS
  GUCs are restored per job, so a job cannot silently operate cross-tenant.
- The `_TenantEnvelope` is **server-authored at enqueue** from a validated
  `TenantContext`; it is never accepted from a client. (Redis payloads are
  trusted infra, same as the DB.)
- RLS readiness now extends to the worker fleet — required before any
  autonomous publish/sync job ships.
- No new secrets. No new external surface. Redis is already a dependency.

**Residual risk:** a developer could call raw `enqueue_job` and bypass the
envelope. Mitigation: a lint/review rule + the reference test asserting the
decorator is present; document `enqueue_tenant_job` as the only sanctioned
path.

---

## 5. Rollback plan

Lowest-risk phase in the program — **nothing currently depends on jobs.**
- The web app runs unchanged whether or not the worker is running; the ARQ
  pool in lifespan is optional (wrapped, logs + continues if Redis absent).
- Rollback = stop the worker process and/or revert `aicmo/queue/*`. No
  data migration to reverse, no request-path change to undo.
- A kill switch `JOBS_ENABLED` (default true) lets ops disable enqueue
  globally without a deploy (enqueue becomes a logged no-op).

---

## 6. Success metrics

- ✅ Reference job, run via the harness, sees **only its tenant's rows**
  under RLS-on (automated isolation test — mirrors `tests/rls/`).
- ✅ Every enqueued job payload carries a `_TenantEnvelope` (unit test on
  `enqueue_tenant_job`).
- ✅ structlog lines + Sentry events from inside a job carry
  `organization_id`/`brand_id` (assert binding).
- ✅ Worker process leaks no tenant tags between consecutive jobs
  (`clear_tenant_context` test).
- ✅ Full backend suite stays green; zero request-path regressions.

---

## 7. Reuse map (no rewrites)

| Reused | From |
|---|---|
| `bind_contextvars` / `bind_tenant_context` / `clear_tenant_context` | `observability/sentry.py`, `tenancy` |
| `rls.set_request_context` / `set_bypass` | `db/rls.py` (Phase-RLS) |
| `SessionLocal` | `db/session.py` |
| `TenantContext` | `tenancy/context.py` |
| `WorkerSettings` skeleton | `queue/worker.py` |
| `modules/<name>/tasks.py` convention | CLAUDE.md |

## 8. Task breakdown (for execution after approval)

1. `queue/enqueue.py` — `enqueue_tenant_job` + `_TenantEnvelope`.
2. `queue/context.py` — `@tenant_job` decorator + session/RLS/log wiring.
3. `queue/reference.py` — reference job (test-only).
4. `main.py` lifespan + `get_arq_pool` dep + `JOBS_ENABLED` flag in config.
5. `WorkerSettings.functions` ← `ALL_JOBS` registry.
6. `tests/queue/` — isolation, envelope, binding, leak, no-op-when-disabled.
7. Gates: pytest + (worker boots) + docs note in CLAUDE.md.
