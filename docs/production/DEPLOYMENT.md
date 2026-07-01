# Deployment Guide

DM Tool is a monorepo deployed as two services:

- **Frontend** — `apps/web` (Next.js 15) on **Vercel**.
- **Backend** — `apps/api` (FastAPI) on **Render**, plus an Arq **worker**, a
  managed **Postgres**, and a managed **Redis**. Provisioned by
  [`render.yaml`](../../render.yaml).

```
 Browser ──▶ Vercel (Next.js)  ──HTTPS──▶  Render web (FastAPI)
                                              ├─▶ Postgres (managed)
                                              ├─▶ Redis (Arq broker)
                                              └─  Render worker (Arq: publish cron, jobs)
```

---

## 1. Backend — Render

The blueprint (`render.yaml`) defines `dm-tool-api` (web), `dm-tool-worker`,
`dm-tool-db` (Postgres), `dm-tool-redis`.

- **Root dir**: `apps/api`
- **Build**: `pip install uv && uv sync --frozen --no-dev`
- **Start** (web): `bash start.sh` → runs `alembic upgrade head` **then**
  `uvicorn aicmo.main:app`. Migrations run at container start because Render's
  free tier has no pre-deploy hook. If migrations fail, the container exits
  non-zero and Render marks the deploy failed (never serves a half-migrated app).
- **Start** (worker): `uv run arq aicmo.queue.worker.WorkerSettings`
- **Health check path**: `/health`

`DATABASE_URL` and `REDIS_URL` are injected from the managed services. All other
env vars: set in the Render dashboard (see [ENVIRONMENT.md](ENVIRONMENT.md)).
Secrets are `sync: false` in the blueprint — enter them in the dashboard, never
in git.

## 2. Frontend — Vercel

- **Root directory**: `apps/web` (the repo root is the monorepo; Vercel must
  point at `apps/web`).
- **Framework preset**: Next.js (auto-detected).
- **Env vars**: the `NEXT_PUBLIC_*` set (see ENVIRONMENT.md). `NEXT_PUBLIC_API_URL`
  must be the Render backend origin; `NEXT_PUBLIC_AUTH_MODE` must equal the
  backend `AUTH_MODE`.
- Security headers (CSP/HSTS/nosniff/…) are configured in `apps/web/next.config.ts`.

## 3. CORS wiring

`API_CORS_ORIGINS` (Render) **must** contain the exact Vercel origin
(`https://<project>.vercel.app` and any custom domain). Mismatch → the browser
blocks API calls with a CORS error.

---

## First production deploy — checklist

1. **Clerk** (production instance): create it, set `AUTH_MODE=clerk` +
   `NEXT_PUBLIC_AUTH_MODE=clerk` and all `CLERK_*` / `NEXT_PUBLIC_CLERK_*` vars.
   Verify `CLERK_JWT_ISSUER` exactly matches the token `iss` (no trailing slash).
2. **Secrets**: set `IP_HASH_PEPPER`, `MEDIA_SIGNING_SECRET`, `SENTRY_DSN`,
   `ANTHROPIC_API_KEY`, `API_CORS_ORIGINS`, `PUBLIC_BASE_URL`. The boot guard
   refuses to start with placeholders when `API_ENV=production`.
3. **Storage**: leave `MEDIA_BACKEND=local` unless object storage is configured.
   Image generation + exports stay safely disabled until then (see
   [object-storage.md](object-storage.md)).
4. **Deploy backend** (Render blueprint) → wait for `/health` = 200 and
   `alembic upgrade head` success in logs.
5. **Deploy frontend** (Vercel) with `NEXT_PUBLIC_API_URL` = the Render origin.
6. **Smoke test**: sign in, create a workspace, load the dashboard, create a lead.
7. Feature flags stay OFF (Studio/Poster/Video/Billing) until explicitly enabled.

---

## Database migrations

- Alembic; revisions in `apps/api/alembic/versions/`. All 45 revisions define
  both `upgrade()` and `downgrade()` (reversible).
- Applied automatically at web-container start (`start.sh`). No manual step.
- **Forward-only in practice**: prefer additive migrations. To roll back a bad
  migration, redeploy the previous image (see below) — a schema downgrade in
  production should be a deliberate, reviewed action, not a routine rollback.

## Rollback

- **Frontend**: Vercel → Deployments → promote the previous deployment (instant).
- **Backend**: Render → Deploys → "Rollback" to the previous successful deploy.
  Because migrations run on start and are additive, rolling the app back one
  version is safe as long as the previous version is compatible with the current
  schema (it is, for additive migrations).
- **If a migration itself is the problem**: fix forward (a new migration) rather
  than downgrading in place; the guard in `0032_rls_policies` and the existence
  checks make fresh + existing DBs converge.

## Deployment safety properties

- Migrations gate the server start (fail closed).
- Boot guards: `assert_auth_config_valid()` (auth mis-config → refuse start) and
  `validate_production_secrets()` (placeholder secrets in prod → refuse start).
- The worker and web share DB + Redis; the web degrades gracefully if Redis is
  down (job enqueue becomes a logged no-op).
- Health: `/health` (liveness) and `/readyz` (DB + Redis + queue readiness → 503
  when a hard dependency is down).
