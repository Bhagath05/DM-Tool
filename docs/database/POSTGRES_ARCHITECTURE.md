# DM Tool — PostgreSQL Architecture Review

> Decision of record: **PostgreSQL is the primary database and the long-term
> strategy.** No MongoDB migration. All migrations continue through Alembic.
> Date: 2026-06-11. Engine: PostgreSQL 16.14 (dev: `postgres:16-alpine`).

---

## 0. Scope

This review covers the current schema, index gaps (and what migration 0031
fixed), Row-Level-Security readiness, pgvector preparation, transaction
usage, the application+database tenant-isolation model, and the
operational posture (backup, DR, performance, security).

---

## 1. Current schema

### 1.1 Shape

43 tables in the `public` schema, organized into three concerns:

| Concern | Representative tables |
|---|---|
| **Identity & tenancy** | `users`, `organizations`, `organization_members`, `brands`, `roles`, `permissions`, `role_permissions`, `member_roles`, `organization_invites` |
| **Business / generated assets** | `business_profiles`, `generated_content`, `generated_ads`, `generated_visuals`, `rendered_visuals`, `campaign_plans`, `bundles`, `trend_reports`, `landing_pages`, `leads`, `social_*`, `learning_*`, `performance_*` |
| **Platform / security / billing** | `audit_events`, `ai_audit_events`, `security_events`, `user_sessions`, `notification_preferences`, `integration_connections`, `integration_credentials`, `subscriptions`, `invoices`, `usage_events`, `rate_limit_buckets` |

### 1.2 Tenancy columns (the RLS-critical invariant)

Every business/asset table inherits `TenantMixin` (`apps/api/aicmo/db/base.py`):

```python
class TenantMixin:
    organization_id: Mapped[uuid.UUID]  # FK organizations, NOT NULL, index=True
    brand_id:        Mapped[uuid.UUID]  # FK brands,        NOT NULL, index=True
```

This is the single most important fact for the database layer: **every
tenant-scoped row carries a NOT NULL `organization_id`**, which is exactly
what an RLS policy keys on. The schema is already RLS-shaped (see §3).

Legacy `user_id` (String) columns survive on the asset tables from the
pre-tenancy era. They are no longer the access path — services filter by
`brand_id` — but they remain for attribution/back-compat.

### 1.3 Keys & types

- **Primary keys**: `uuid` (`gen_random_uuid()` server-side or `uuid4()`
  app-side). No integer surrogate keys — good for multi-tenant systems
  (no cross-tenant key guessing, merge-friendly).
- **JSONB** for all structured LLM output (`output`, `strategy`,
  `targeting`, `calendar`, `analysis`, `metadata_json`). Validated by
  Pydantic before insert — the DB stores already-shaped documents.
- **Enums as `String` + CHECK** (e.g. `organizations.status IN (...)`)
  rather than native PG `ENUM` — deliberate, because PG enums are
  migration-heavy to extend.
- **Timestamps**: `TIMESTAMPTZ` via `TimestampMixin` (`created_at`,
  `updated_at` with `server_default=now()` and `onupdate`).

### 1.4 Constraints worth noting

- `organizations.slug` — global UNIQUE (`uq_organizations_slug`).
- `brands` — partial UNIQUE on `(organization_id, slug)` among non-deleted.
- `brands` — partial UNIQUE `(organization_id) WHERE is_default` (one
  default brand per org; the DB owns this invariant).
- `rate_limit_buckets` — UNIQUE `(key, window_start)` (`uq_rl_key_window`),
  used by the fixed-window limiter's UPSERT.
- CHECK constraints on every status column.

---

## 2. Missing indexes (and what migration 0031 fixed)

### 2.1 The gap

Pre-tenancy, list queries filtered by `user_id`. The composite indexes
reflected that: `ix_leads_user_created (user_id, created_at)`,
`ix_leads_user_status (user_id, status)`. After W1-11, **every service
filters by `brand_id`**:

```python
select(Lead).where(Lead.brand_id == tenant.brand_id).order_by(desc(Lead.created_at))
select(GeneratedAd).where(GeneratedAd.brand_id == ...).order_by(desc(...))
# ...content, campaigns, bundles — identical shape
```

`TenantMixin` provides a single-column `brand_id` index, so these weren't
table scans — but Postgres still had to sort by `created_at` after the
index filter, and the legacy `(user_id, …)` composites were dead weight on
writes. Two genuine gaps were worse:

- **`audit_events.organization_id`** — a plain foreign key. **Postgres does
  not auto-index foreign keys.** The org activity report
  (`SELECT max(occurred_at) WHERE organization_id = ?`) had no covering
  index.
- **`organization_members`** — the tenant resolver runs
  `WHERE user_id = ? AND status = 'active'` on **every authenticated
  request**. *Verified caveat:* this path was **already** served by the
  pre-existing partial unique index `uq_org_members_org_user_active`
  (whose leading column is `user_id`), so it was NOT actually unindexed.
  The two indexes 0031 adds here are **supplementary** — `(user_id, status)`
  for status-filtered member lists and `(organization_id, user_id)` for
  reverse lookups — not the critical fix.

### 2.2 The fix — migration `0031_tenant_performance_indexes.py`

Additive, idempotent (`CREATE INDEX IF NOT EXISTS`), fully reversible.
**19 indexes** across the five named domains, **applied and verified live**
(all 19 present + valid; `EXPLAIN` confirms the leads/campaigns/ads list
sorts and the audit-events org report now use the new indexes):

| Domain | Indexes added |
|---|---|
| **leads** | `(brand_id, created_at DESC)`, `(brand_id, status)`, `(organization_id, created_at DESC)` |
| **campaign_plans** | `(brand_id, created_at DESC)`, `(brand_id, campaign_type)`, `(brand_id, created_at DESC) WHERE is_saved` |
| **generated_content** | `(brand_id, created_at DESC)`, `(brand_id, content_type)`, `(brand_id, created_at DESC) WHERE is_saved` |
| **generated_ads** | `(brand_id, created_at DESC)`, `(brand_id, ad_type)`, `(brand_id, created_at DESC) WHERE is_saved` |
| **audit_events** | `(organization_id, occurred_at DESC)`, `(actor_user_id)`, `(brand_id) WHERE brand_id IS NOT NULL` |
| **organizations** | `(owner_user_id)`, `(status) WHERE status = 'active'` |
| **organization_members** | `(user_id, status)`, `(organization_id, user_id)` |

Design notes:
- **Partial `WHERE is_saved`** indexes — saved assets are a small subset;
  the partial index is a fraction of the size and exactly matches the
  "favourites" filter.
- **`created_at DESC`** matches the `ORDER BY ... DESC` so the planner reads
  the index in physical order (no sort node).
- The legacy `ix_leads_user_*` indexes are **left in place** — dropping
  them is a separate, riskier change (some attribution queries may still
  use them). Tracked as a Tier-3 cleanup once query logs confirm they're
  cold.

### 2.3 Still-thin areas (recommended next)

| Table | Suggested index | Why |
|---|---|---|
| `ai_audit_events` | already has 5 (migration 0030) | ✅ covered |
| `security_events` | `(organization_id, created_at DESC)` | session/security timeline |
| `usage_events` | `(organization_id, created_at)` | billing rollups |
| `landing_pages` | `(brand_id, status)` | public-page lookups |
| `integration_connections` | `(organization_id, provider, status)` | connector dashboards |
| `leads` | `(brand_id, email)` | dedupe / lookup by email within brand |

These weren't in the approved scope (orgs/campaigns/leads/content/audit) —
listed here for the backlog.

### 2.4 Index rollout on large tables

Migration 0031 uses plain `CREATE INDEX` (instant on today's small tables,
runs inside Alembic's transaction). **When any table exceeds ~1M rows**,
build the index without the write lock:

```sql
-- Run OUTSIDE a transaction (psql, not inside alembic's txn):
CREATE INDEX CONCURRENTLY ix_leads_brand_created ON leads (brand_id, created_at DESC);
```

In Alembic, that means a migration with
`op.execute("COMMIT")` + `op.create_index(..., postgresql_concurrently=True)`
or running the DDL out-of-band and `alembic stamp`-ing. Documented here so
the pattern is known before it's needed.

---

## 3. RLS readiness

> **Update (Phase DB-RLS): readiness now IMPLEMENTED, not just designed.**
> Policies + helper functions are installed dormant (migration 0032), the
> `DB_RLS_ENABLED` flag + resolver/onboarding GUC wiring are shipped (no-op
> while off), activation/rollback scripts exist, and 15 tests pass
> (including live tenant-A-vs-B isolation, cross-tenant write block, and
> reversibility). Full runbook: `docs/database/RLS_ACTIVATION.md`.

### 3.1 Current posture

Tenant isolation today is enforced **at the application layer**: every
protected route depends on `require_tenant()` / `require_permission()`, and
every service query carries an explicit `WHERE brand_id = ?` /
`WHERE organization_id = ?`. The 10 pinned invariants in
`tests/tenancy/test_security_invariants.py` guard this.

RLS would add a **second, database-enforced** layer: even a service query
that *forgot* its `WHERE brand_id` clause could not return another tenant's
rows. This is defense-in-depth (OWASP A01), not a replacement for the app
layer.

### 3.2 Why the schema is already RLS-ready

- Every tenant table has `organization_id NOT NULL` — the policy predicate
  column exists and can never be NULL (no "leaky" rows).
- UUID tenant keys — no sequence-guessing across tenants.
- A single, consistent column name (`organization_id`) across all tables —
  one policy template applies everywhere.

### 3.3 The activation plan (NOT yet applied — deliberate)

RLS is **designed but not enabled**, because turning it on without the
session-GUC wiring below would make every query return zero rows and take
the product down. Activation is a coordinated two-part change:

**Part A — session GUC wiring (application).** After the tenant resolver
computes `organization_id`, set a transaction-local GUC so the policy can
read it:

```python
# In tenancy/dependencies.py:require_tenant, after org is resolved,
# inside the request's transaction:
await session.execute(
    text("SET LOCAL app.current_org_id = :org"),
    {"org": str(tenant.organization_id)},
)
```

`SET LOCAL` is scoped to the transaction and cleared on commit/rollback —
safe with a pooled connection.

**Part B — the RLS migration (ready to apply).** A helper function + one
policy per tenant table:

```sql
-- Reader for the per-request GUC. STABLE so the planner can cache it.
CREATE OR REPLACE FUNCTION app_current_org() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
$$;

-- Per tenant table (template):
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads FORCE ROW LEVEL SECURITY;   -- applies even to the table owner
CREATE POLICY tenant_isolation_leads ON leads
  USING (organization_id = app_current_org())
  WITH CHECK (organization_id = app_current_org());
-- repeat for: generated_content, generated_ads, generated_visuals,
--   rendered_visuals, campaign_plans, bundles, business_profiles,
--   landing_pages, trend_reports, social_*, learning_*, performance_*,
--   audit_events, ai_audit_events, security_events, user_sessions, ...
```

Notes:
- `FORCE ROW LEVEL SECURITY` is required because the app connects as the
  table owner, who bypasses RLS by default.
- A **migration/admin role** that needs cross-tenant access (Alembic, the
  org-creation path that runs *before* a tenant exists, backfills) must be
  `BYPASSRLS` or excepted via a policy `USING (app_current_org() IS NULL)`
  for the bootstrap path. The onboarding `create_workspace` flow runs with
  no tenant yet — it must be on a `BYPASSRLS` role or explicitly carved out.

**Roll-out order**: ship Part A first (harmless no-op until policies exist),
confirm the GUC is set on every request via a canary, then ship Part B
table-by-table behind a flag, running the tenancy invariant suite against a
live RLS-enabled Postgres after each.

### 3.4 Acceptance test for RLS

Before enabling in production, this must pass against a live DB:

```sql
SET app.current_org_id = '<org-A>';
SELECT count(*) FROM leads;          -- only org-A rows
SET app.current_org_id = '<org-B>';
SELECT count(*) FROM leads;          -- only org-B rows
RESET app.current_org_id;
SELECT count(*) FROM leads;          -- 0 rows (fail closed)
```

---

## 4. pgvector integration prep

### 4.1 Current state

- The dev image is `postgres:16-alpine`, which **does not bundle pgvector**.
- No embeddings are stored today (per CLAUDE.md: "Vector retrieval is not in
  MVP").

### 4.2 Readiness checklist (for when embeddings land)

1. **Swap the image** to one that ships the extension:
   ```yaml
   # infra/docker-compose.yml
   image: pgvector/pgvector:pg16     # drop-in, same PG 16 + the vector ext
   ```
   In managed Postgres (RDS/Cloud SQL/Supabase), pgvector is available as
   an installable extension — no image change, just `CREATE EXTENSION`.

2. **Enable the extension** (a guarded migration):
   ```python
   def upgrade() -> None:
       op.execute("CREATE EXTENSION IF NOT EXISTS vector")
   ```
   This is intentionally NOT in migration 0031 — the alpine image would
   fail it. Add it in the migration that introduces the first embedding
   column, once the image supports it.

3. **Embedding table shape** (recommended, tenant-scoped + RLS-ready):
   ```sql
   CREATE TABLE content_embeddings (
       id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
       organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
       brand_id        uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
       source_type     text NOT NULL,        -- 'content' | 'ad' | 'trend' | ...
       source_id       uuid NOT NULL,
       embedding       vector(1536),         -- match the embedding model's dim
       created_at      timestamptz NOT NULL DEFAULT now()
   );
   -- ANN index (build after data exists; HNSW is the modern default):
   CREATE INDEX ix_content_embeddings_hnsw
     ON content_embeddings USING hnsw (embedding vector_cosine_ops);
   -- Tenant filter still indexed for pre-filtering:
   CREATE INDEX ix_content_embeddings_brand ON content_embeddings (brand_id);
   ```
   - Keep `organization_id` NOT NULL so the same RLS policy template applies.
   - **Pre-filter by `brand_id`, then ANN-search** — never ANN-search across
     tenants. (Partitioning or a `WHERE brand_id = ?` before the `<=>`
     operator keeps results tenant-scoped.)

4. **Dimension** must match the embedding model (e.g. 1536 for
   `text-embedding-3-small`). Pin it in config so the migration and the
   embedder agree.

---

## 5. Transactions for critical operations

### 5.1 Current posture (verified)

- **One async session per request** (`get_db` yields `SessionLocal()`),
  `expire_on_commit=False`, `pool_pre_ping=True`.
- **Multi-step writes are single-transaction.** The exemplar is onboarding
  `create_workspace` (org + brand + member + role + 3 audit rows in ONE
  transaction, all-or-nothing — see CLAUDE.md "Entity creation order").
- **Audit + AI-audit rows commit in the same transaction as the action**
  they describe (`audit_service.record` / `record_ai_generation` call
  `flush()`, the caller `commit()`s). Correct: no audit-of-an-event-that-
  rolled-back.
- **Rate-limit UPSERT** is atomic (`INSERT ... ON CONFLICT DO UPDATE
  RETURNING count`), one round-trip.

### 5.2 Recommendations

| Item | Recommendation |
|---|---|
| Isolation level | Default `READ COMMITTED` is correct for this workload. Reserve `SERIALIZABLE` for the rare invariant-critical path (e.g. last-owner removal) and retry on `40001`. |
| Long transactions | LLM calls must **never** be inside an open DB transaction (they take seconds). Current design already does this — generation happens, *then* the row + audit are written and committed. Keep this rule explicit. |
| Idempotency | Generation endpoints aren't idempotent — a client retry creates a second asset. Consider an `Idempotency-Key` header → unique partial index for paid/critical generations (Tier 3). |
| Advisory locks | For the "one default brand per org" race, the partial unique index already fails-closed. No advisory lock needed. |

---

## 6. Tenant isolation — application + database layers

| Layer | Mechanism | Status |
|---|---|---|
| **Edge** | Tenant headers `X-Organization-Id` / `X-Brand-Id` are **untrusted** input | ✅ |
| **Application** | `require_tenant()` re-resolves + validates membership from the DB on **every** request; services filter by `brand_id` | ✅ enforced, 10 pinned invariants |
| **Schema** | `organization_id NOT NULL` on every tenant table; UUID keys | ✅ RLS-ready |
| **Database (RLS)** | Row-Level-Security policies | 🚧 designed, not enabled (§3) |

The trust boundary is the backend resolver + DB, never the client (see
CLAUDE.md "Trust boundaries"). RLS (§3) closes the residual risk that a
*new* service query forgets its `WHERE brand_id` clause — today that's
caught only by code review and tests; RLS would make it structurally
impossible.

---

## 7. Backup strategy

> Current state: **dev-only, no automated backups.** The compose stack runs
> a single Postgres container with a local volume. This is the single
> biggest operational gap before production.

Recommended posture (managed Postgres — RDS / Cloud SQL / Supabase):

| Tier | Mechanism | Target |
|---|---|---|
| **Continuous** | WAL archiving / PITR (point-in-time recovery) | RPO ≤ 5 min |
| **Daily** | Automated full snapshot, 30-day retention | nightly |
| **Weekly** | Snapshot copied to a **second region / account** | offsite |
| **Pre-migration** | Manual snapshot immediately before every `alembic upgrade` in prod | per-deploy |
| **Logical** | Weekly `pg_dump --format=custom` to object storage (portable, version-independent restore) | weekly |

Operational rules:
- **Encrypt backups at rest** (KMS) and **in transit**.
- **Test restores quarterly** — a backup you've never restored is a
  hypothesis, not a backup.
- Backups inherit the data's sensitivity: lead PII + encrypted OAuth tokens
  live here. Restrict who can download/restore (audit it).

---

## 8. Disaster recovery plan

| Objective | Target | How |
|---|---|---|
| **RPO** (max data loss) | ≤ 5 min | Continuous WAL archiving / PITR |
| **RTO** (max downtime) | ≤ 1 hour | Restore latest snapshot + replay WAL, or promote a read replica |

**Topology recommendation (production):**
- Primary + **synchronous or async standby replica** in a second AZ.
- Promote the replica on primary failure (managed services automate this).
- Cross-region snapshot copy for region-level failure.

**Runbook (primary failure):**
1. Confirm primary is actually down (not a network blip) — check from two
   vantage points.
2. Promote the standby (or restore the latest snapshot + WAL to a new
   instance).
3. Repoint `DATABASE_URL` (secret store → rolling restart of the API). The
   app reconnects via SQLAlchemy's `pool_pre_ping`.
4. Verify: `/health`, then the tenancy smoke (`/api/v1/users/me`) for a
   known org, then a read of `leads` for a known brand.
5. Post-incident: confirm WAL continuity, re-establish a fresh standby,
   write the incident note.

**Migration safety:** every production `alembic upgrade` is preceded by a
manual snapshot (§7). Every migration in this repo has a tested
`downgrade()` — rollback is `alembic downgrade -1` + (if needed) snapshot
restore.

**Dependencies to DR-plan alongside Postgres:**
- `INTEGRATION_TOKEN_KEY` (Fernet) — if lost, every stored OAuth token is
  unrecoverable. Back up the KMS/secret, not just the DB.
- Redis (`rate_limit_buckets` is in PG, but Arq job state is in Redis) —
  ephemeral; jobs should be replayable.

---

## 9. Performance bottlenecks

| # | Bottleneck | Severity | Mitigation |
|---|---|---|---|
| 1 | Brand-scoped list sorts without composite index | High | **Fixed** in migration 0031 |
| 2 | `audit_events.organization_id` FK unindexed (org activity report) | High | **Fixed** in migration 0031 (`ix_audit_events_org_occurred`) |
| 3 | Tenant resolver runs the `MemberRole ⨝ RolePermission ⨝ Permission` join on **every** request, no caching | Medium | Membership lookup already indexed (pre-existing `uq_org_members_org_user_active`); consider a short per-request permission cache (Tier 3) |
| 4 | Rate-limit middleware adds 1 DB round-trip per `/api/*` request | Medium | Fail-open today; move to Redis `INCR` when load demands (one-file swap, same `consume()` signature) |
| 5 | Large JSONB blobs (`output`, `calendar`) read on every list query via `SELECT *` | Medium | Select only list-needed columns, or move heavy JSONB behind a detail fetch (Tier 3) |
| 6 | No connection pooler in front of Postgres | Medium (at scale) | Add **PgBouncer** (transaction pooling) before the connection count climbs; SQLAlchemy pool is per-process |
| 7 | `pool_pre_ping=True` adds a round-trip per checkout | Low | Acceptable; keeps stale-connection failures out of requests |
| 8 | Opportunistic rate-limit cleanup runs inline ~1% of submits | Low | Fine at current scale; move to a scheduled job later |

**Observability gap:** no `pg_stat_statements` enabled. Turn it on in
production to find the real slow queries instead of guessing:
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- then: SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;
```

---

## 10. Security recommendations

| Area | Status | Recommendation |
|---|---|---|
| Tenant isolation (app) | ✅ enforced + tested | Keep the 10 invariants green in CI |
| Tenant isolation (DB) | 🚧 RLS designed | Activate RLS (§3) for defense-in-depth |
| PII at rest | ⚠️ lead PII + Fernet-encrypted OAuth tokens in plain tables | Consider column-level encryption / `pgcrypto` for the most sensitive PII; ensure backups are KMS-encrypted |
| IP addresses | ✅ hashed (`ip_hash`, SHA-256 + pepper) | Already GDPR-aware; never store raw IPs |
| Least privilege | ⚠️ app connects as a superuser-ish owner in dev | In prod, run the app as a **non-superuser** role with only DML on app tables (no `DROP`, no `BYPASSRLS` except the carved-out bootstrap role) |
| Connection security | ⚠️ dev uses plaintext | **Require TLS** (`sslmode=require`/`verify-full`) for all non-local connections |
| Secrets | ✅ runbook exists | `DATABASE_URL` rotation procedure is in `docs/security/SECRETS.md` |
| Audit immutability | ✅ append-only in app | Consider revoking `UPDATE`/`DELETE` on `audit_events` + `ai_audit_events` at the DB-grant level so even a compromised app can't rewrite history |
| Backup security | ⚠️ none yet | Encrypt + restrict + audit access (§7) |
| `search_path` | — | Pin `search_path = public` on the app role to avoid schema-shadowing attacks |

---

## 11. Summary scorecard

| Dimension | Before | After (this review) |
|---|---|---|
| Hot-path indexes (5 named domains) | legacy `user_id`, FK gaps | ✅ composite brand/org indexes (migration 0031) |
| RLS readiness | schema-ready, undocumented | ✅ designed, activation plan + acceptance test |
| pgvector readiness | none | ✅ image + extension + table + ANN-index plan |
| Transaction discipline | correct, undocumented | ✅ verified + documented + Tier-3 idempotency note |
| Tenant isolation | app-layer only | app-layer ✅ + DB-layer RLS plan |
| Backup / DR | none (dev) | ✅ documented strategy + runbook (impl pending infra) |
| Observability | none | `pg_stat_statements` + `pg_stat_statements`-driven tuning recommended |

**Shipped in this pass:** migration `0031_tenant_performance_indexes.py`
(19 additive indexes, applied + verified live), this review, the RLS
activation plan, and the pgvector readiness plan. **Pending (infra, not code):** automated backups,
standby replica, PgBouncer, TLS enforcement, least-privilege DB role,
RLS activation behind a flag.
