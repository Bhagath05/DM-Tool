# Operations, Monitoring & Troubleshooting

## Health & readiness

| Endpoint | Purpose | Behaviour |
|---|---|---|
| `GET /health` | Liveness | Cheap; never touches dependencies. Render's health check path. |
| `GET /readyz` | Readiness | Validates Postgres + Redis + job queue. **503** when a hard dependency is down so a load balancer stops routing. |
| `GET /api/v1/system/storage` | Storage capability | Auth-required; reports `media_backend` + `media_persistence_available` (drives the Studio admin notice). |

## Logging

- **Structured JSON** (structlog) → stdout → Render log stream.
- **Every log line carries the request context**: `request_id` (from
  `RequestIDMiddleware`, also returned as the `X-Request-Id` response header)
  and, once the tenant is resolved, `user` / `organization_id` / `brand_id` /
  `role` (bound by the tenant resolver, surfaced via the `merge_contextvars`
  processor).
- **To debug a customer issue**: get the `X-Request-Id` from their response (or
  ask support to capture it), then filter Render logs by that id to see the full
  request trace; filter by `organization_id` to see all of a tenant's activity.
- **Never logged**: JWTs, OAuth tokens, secrets, raw IPs (IPs are SHA-256 hashed
  with a pepper). Sentry additionally scrubs `Authorization` / `Cookie` /
  `X-API-Key` / `Set-Cookie`.

## Error reporting (Sentry)

- Backend `SENTRY_DSN` + frontend `NEXT_PUBLIC_SENTRY_DSN`. Empty = disabled (dev).
- 5xx responses auto-report; 4xx do not (user/input error, avoids noise).
- Events carry tenant tags when the SDK is initialised.
- `GET /api/v1/debug/sentry-config` (dev/staging only) verifies wiring.

## Background jobs & cron (Arq worker)

- `dm-tool-worker` runs `aicmo.queue.worker.WorkerSettings`.
- **Cron**: `publish_due_scheduled_posts` (every minute) auto-publishes due
  scheduled posts; `monitor_system_cron` (every minute) system health.
- **Retries**: publishing retries up to `MAX_PUBLISH_ATTEMPTS` (3); a permanently
  failed post is recoverable via `POST /publishing/posts/{id}/retry`. Every
  attempt is recorded as a `PublishEvent` (audit trail).
- Redis uses `maxmemoryPolicy: noeviction` so queued jobs are never dropped.

## Rate limiting

Per-IP fixed-window buckets (Postgres-backed): `general` 300/min, `gen` (AI
generation) 60/min, `public` (unauth) 30/min. Lead capture has an additional
tighter per-hashed-IP bucket. A limited request gets **429**.

## Timeouts

All outbound provider calls (`httpx`) set explicit timeouts (4–120s by call
type). LLM generation calls have their own timeouts with deterministic
fallbacks so a slow provider degrades rather than hangs.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend won't boot; `FATAL: AUTH_MODE=...` | `AUTH_MODE=clerk` in prod without valid Clerk vars | Set `CLERK_JWT_ISSUER` + `CLERK_JWKS_URL` (real, not placeholder). |
| Backend won't boot; "missing or placeholder secrets" | A required prod secret is empty/placeholder | Fill it in Render (see ENVIRONMENT.md). |
| `401 Invalid token` on API calls | `CLERK_JWT_ISSUER` mismatch or a stray `CLERK_JWT_AUDIENCE` | Match `iss` exactly; clear `CLERK_JWT_AUDIENCE` if tokens have no `aud`. Check logs for `auth.token_rejected reason=...`. |
| CORS error in browser | `API_CORS_ORIGINS` missing the Vercel origin | Add the exact origin (scheme + host), redeploy. |
| Image generation returns **409 `object_storage_required`** | `MEDIA_BACKEND=local` in production | Configure R2/S3 (object-storage.md); until then image features stay off by design. |
| `ModuleNotFoundError: psycopg2` | Bare `postgresql://` URL | Handled automatically (config normalizes to `postgresql+psycopg://`); ensure you're on current code. |
| `relation "..." does not exist` on fresh DB | Migration ordering | Fixed (existence-guarded RLS migration); run `alembic upgrade head` from base. |
| Scheduled post stuck `failed` | Hit max attempts / provider rejected | Inspect `GET /publishing/posts/{id}/events`; fix the connection; `POST .../retry`. |
| `/readyz` = 503 | Postgres or Redis down | Check the managed service status; the web still serves liveness but degraded. |

## Known limitations (as of launch)

- **Object storage deferred**: image generation + file exports are disabled in
  production until R2/S3 is configured (deliberate — no silent asset loss).
- **Dark features**: Creative Studio, LinkedIn Poster, Video, and Billing ship
  behind flags (complete + tested, not enabled).
- **RLS dormant**: tenant isolation is enforced at the application layer
  (`require_tenant`/`require_permission`, CI-guarded); Postgres RLS policies
  exist but are not enabled (defence-in-depth, `DB_RLS_ENABLED=false`).
- **Arq jobs** carry tenant scope via explicit payload args, not ambient
  contextvars (tracked).
- **Two pre-existing test-only failures** deferred to a dedicated sprint
  (`clerk-token-bridge`, poster `clamp`) — no production impact.
- Live platform publishing requires each platform's OAuth app to be configured;
  until then those integrations stay behind availability flags.

## Roadmap

See [docs/product/ROADMAP.md](../product/ROADMAP.md) and the Phase 3
autonomous-architecture design (Decision Engine → Planner → Agents → Approval
Queue), which ships behind flags with execution OFF by default.
