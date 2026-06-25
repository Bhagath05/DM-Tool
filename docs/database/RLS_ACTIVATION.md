# RLS Activation Checklist & Rollback Plan

> Status: **READINESS COMPLETE — NOT ACTIVATED.** Policies are installed
> and dormant. This document is the runbook to turn enforcement ON when
> the org is ready (enterprise / SOC2), and to roll it back fast.

---

## 0. What "readiness" shipped

| Artifact | What it does | State |
|---|---|---|
| `aicmo/db/rls.py` | Single source of truth: GUC names, policy/function DDL, runtime helpers | shipped |
| Migration `0032_rls_policies.py` | Creates 3 helper functions + 6 policies, **RLS not enabled** (dormant) | applied |
| `DB_RLS_ENABLED` flag (`config.py`) | When true, resolver sets per-request GUCs | **false** (default) |
| Resolver wiring (`tenancy/dependencies.py`) | Bypass during resolution → org/user GUC for the request body | shipped, no-op while flag off |
| Onboarding wiring (`orgs/service.py:create_workspace`) | Bypass for the pre-tenant org-creation txn | shipped, no-op while flag off |
| `scripts/rls_activate.py` / `rls_deactivate.py` | Deliberate ENABLE/FORCE / DISABLE toggle | ready |
| `tests/rls/test_rls_policies.py` | 15 tests: isolation, cross-tenant write block, bypass, fail-closed, reversibility | passing |

**The two-switch model.** Enforcement requires BOTH:
1. `DB_RLS_ENABLED=true` — so the app sets `app.current_org_id` per request.
2. `scripts/rls_activate.py` — so Postgres enforces the policies.

Neither alone breaks anything: policies are dormant until enabled; GUCs
are harmless until policies read them. This is what makes activation safe
and staged.

---

## 1. Architecture recap (what gets enforced)

- **Boundary: organization.** Policies key on
  `organization_id = app_current_org()`. The org is the tenant boundary.
  Brand-level scoping stays an application concern. Org-level RLS catches
  the catastrophic failure — cross-*tenant* leakage.
- **Policy shapes:**
  - org-scoped (`leads`, `campaign_plans`, `generated_content`,
    `audit_events`): `organization_id = current_org`.
  - `organizations`: the active org OR an org the caller is an active
    member of (keeps the org-switcher membership list working).
  - `users`: the caller's own row OR a user sharing the active org
    (team listings).
- **Bypass** (`app.rls_bypass = 'on'`): explicit, transaction-local
  escape hatch for legitimate pre-tenant / cross-tenant service paths.
- **FORCE ROW LEVEL SECURITY** so the policy applies even to the table
  owner (the app's DB role).

---

## 2. Pre-flight checklist (before activating in ANY environment)

- [ ] Migration `0032_rls_policies` applied (`scripts/rls_activate.py --check`
      shows `policy✓` on all six tables).
- [ ] **App DB role is NOT a superuser and NOT `BYPASSRLS`.** Superusers
      bypass RLS unconditionally — enforcement would be silently inert.
      (Today's dev `aicmo` role IS a superuser; production must use a
      restricted role. See `docs/database/POSTGRES_ARCHITECTURE.md` §10.)
- [ ] A dedicated **migration/admin role** (Alembic, backfills) has
      `BYPASSRLS` — or every data migration sets `app.rls_bypass='on'`.
- [ ] Every **pre-tenant / cross-tenant service path** sets bypass or the
      right GUC. Audited list below (§3).
- [ ] `DB_RLS_ENABLED=true` set in the target env AND the API restarted
      (settings are cached in `lru_cache`).
- [ ] A fresh **DB snapshot** taken (instant rollback insurance).
- [ ] `rls_deactivate.py` rehearsed in staging (the rollback path works).

---

## 3. Service-account / pre-tenant paths that need bypass or GUC

These run outside a normal tenant-scoped request. Each must set the right
session context once RLS is enforced. **Wired** = done; **TODO** = wire
before activating.

| Path | Why it's special | Status |
|---|---|---|
| `tenancy/dependencies.py:require_tenant` | reads users/orgs before tenant known | ✅ wired (bypass→GUC) |
| `orgs/service.py:create_workspace` (onboarding) | creates the org pre-tenant | ✅ wired (bypass) |
| Alembic migrations / backfills | DDL + cross-tenant DML | ⚠️ use a `BYPASSRLS` admin role |
| Public lead capture (`leads` public router) | org resolved from landing page, no tenant header | ⛔ TODO: set `app.current_org_id` to the resolved org before insert |
| Clerk webhook receiver (`users` upsert) | creates users out-of-band | ⛔ TODO: bypass for the upsert txn |
| Clerk admin sync / security webhooks | cross-tenant | ⛔ TODO: bypass |
| Arq background jobs | no request tenant context | ⛔ TODO: set GUC from job payload's org_id |

The ⛔ rows are why activation is **staged** (§4): enable on the four
fully-wired tables first, leave the webhook/public/job-touched tables
(`users`, `audit_events`) for last, after their paths are wired.

---

## 4. Staged activation procedure

> Do this per environment: **dev → staging → production**. Never jump
> straight to prod.

**Stage A — app sets context (no enforcement yet).**
1. Set `DB_RLS_ENABLED=true`, restart the API.
2. Confirm normal operation (nothing should change — policies dormant).
3. Spot-check a request log / add a temporary assertion that
   `current_setting('app.current_org_id')` is populated mid-request.

**Stage B — enforce the four fully-wired org-scoped tables.**
1. Snapshot the DB.
2. Edit `scripts/rls_activate.py`'s table set OR run the enable SQL for
   just `leads`, `campaign_plans`, `generated_content` first (highest
   value, lowest risk — all reached only via tenant-scoped requests).
   ```bash
   cd apps/api && .venv/bin/python -m scripts.rls_activate   # (all, or scope down)
   ```
3. Run the acceptance test (§6). Exercise the app: list leads, generate
   content, switch orgs.
4. Watch error rates for 24h.

**Stage C — enforce `audit_events`, `organizations`, `users`.**
1. First wire the ⛔ paths in §3 (webhooks, public capture, jobs).
2. Snapshot, enable, acceptance-test, watch.

**Stage D — make it permanent.**
1. Add a chained migration (`0033`) that enables RLS via `rls.enable_sql`
   for all six tables, so a fresh DB comes up enforced — gated on
   `DB_RLS_ENABLED` being true in that environment, OR run activation as
   a documented post-deploy step. (Kept out of the default chain until
   the org commits to always-on RLS.)

---

## 5. Verification — acceptance test

Run as the **app (non-superuser) role**, not the admin role:

```sql
-- A user in org A sees only org A's leads:
SELECT set_config('app.current_org_id', '<org-A-uuid>', false);
SELECT set_config('app.current_user_id', '<user-uuid>', false);
SELECT count(*) FROM leads;                 -- only org A

-- Switch to org B → only org B:
SELECT set_config('app.current_org_id', '<org-B-uuid>', false);
SELECT count(*) FROM leads;                 -- only org B

-- No context, no bypass → zero rows (fail closed):
SELECT set_config('app.current_org_id', '', false);
SELECT set_config('app.rls_bypass', 'off', false);
SELECT count(*) FROM leads;                 -- 0

-- Cross-tenant write blocked:
SELECT set_config('app.current_org_id', '<org-A-uuid>', false);
INSERT INTO leads (organization_id, ...) VALUES ('<org-B-uuid>', ...);  -- ERROR
```

The automated equivalent is `tests/rls/test_rls_policies.py` (15 tests),
which runs the same assertions on a temp table mirroring the production
predicate, plus asserts the real policies are installed and currently
dormant.

---

## 6. Rollback plan

RLS enforcement can be turned off in **seconds, with no app deploy**:

```bash
cd apps/api && .venv/bin/python -m scripts.rls_deactivate
```

This runs `NO FORCE` + `DISABLE ROW LEVEL SECURITY` on all six tables.
The policies remain installed (dormant). The app keeps setting GUCs (a
harmless no-op once nothing reads them); flip `DB_RLS_ENABLED=false` at
leisure.

**Escalating rollback levels:**

| Level | Action | When |
|---|---|---|
| 1 (fastest) | `rls_deactivate.py` | enforcement is causing query failures / empty results |
| 2 | `DB_RLS_ENABLED=false` + restart | also stop the app setting GUCs |
| 3 | `alembic downgrade 0031` (or run `0032` downgrade DDL) | remove the policies + functions entirely |
| 4 | restore the pre-activation snapshot | data-corruption-level incident only |

**Reversibility is tested**: `tests/rls/test_rls_policies.py` covers the
create→drop SQL round-trip, and the live down→up round-trip was verified
(6 policies + 3 functions → 0 → restored).

---

## 7. Failure-mode playbook

| Symptom after enabling | Likely cause | Fix |
|---|---|---|
| App shows **zero rows everywhere** | `DB_RLS_ENABLED` is false (GUCs not set) OR app role is the table owner without the GUC | Set the flag + restart; confirm GUC populated mid-request |
| Onboarding (create org) fails | bypass not set on the pre-tenant txn | already wired; confirm flag on so the wiring runs |
| Public lead capture fails | `leads` enforced before its path was wired | deactivate `leads` OR wire the capture path's GUC (§3) |
| Webhook user-upsert fails | `users` enforced before webhook bypass wired | Stage C ordering — wire first |
| Enforcement seems inert (no isolation) | app connecting as a superuser / `BYPASSRLS` role | switch to a restricted role (§2) |
| Background job can't read its data | job has no tenant GUC | set `app.current_org_id` from the job payload |

---

## 8. SOC2 / enterprise mapping

| Control area | How RLS supports it |
|---|---|
| **CC6.1 logical access** | Tenant isolation enforced at the data layer, not just app code — a forgotten `WHERE` clause cannot leak across tenants. |
| **Defense in depth** | Two independent boundaries (app filter + DB policy) must both fail for a cross-tenant leak. |
| **Auditability** | Enforcement is a discrete, version-controlled toggle (`rls_activate.py`); the policy definition lives in one reviewed file. |
| **Least privilege** | Activation forces the move to a non-superuser app role (pre-flight gate). |
| **Change management** | Staged rollout + tested rollback + snapshot-before-activate. |
| **Separation of duties** | A `BYPASSRLS` admin role is distinct from the app role; bypass is explicit and grep-able. |

---

## 9. Quick command reference

```bash
cd apps/api

# State report
.venv/bin/python -m scripts.rls_activate --check

# Dry run (print the enable SQL, change nothing)
.venv/bin/python -m scripts.rls_activate --dry-run

# Activate enforcement (deliberate)
.venv/bin/python -m scripts.rls_activate

# Roll back enforcement (fast)
.venv/bin/python -m scripts.rls_deactivate

# Run the RLS test suite
.venv/bin/python -m pytest tests/rls/ -v
```
