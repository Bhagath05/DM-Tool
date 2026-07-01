# Production Runbook — Index

Operational documentation for running DM Tool in production. Start here.

## Launch & operate
- [DEPLOYMENT.md](DEPLOYMENT.md) — Render + Vercel deploy, first-deploy checklist, migrations, rollback.
- [ENVIRONMENT.md](ENVIRONMENT.md) — every environment variable: where it's set and when it's required.
- [OPERATIONS.md](OPERATIONS.md) — health checks, logging (`X-Request-Id` + tenant context), monitoring, jobs/cron, rate limiting, troubleshooting, known limitations.
- [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) — backup strategy, restore, disaster scenarios, RPO/RTO.
- [object-storage.md](object-storage.md) — R2/S3 setup + the local-in-prod safety gate.

## Architecture & data
- [/README.md](../../README.md) — stack overview + repo layout (developer onboarding).
- [/CLAUDE.md](../../CLAUDE.md) — product constitution, **auth flow** (AUTH_MODE), **RBAC model**, **tenant model** (end-to-end lifecycle + trust boundaries), conventions.
- [database/POSTGRES_ARCHITECTURE.md](../database/POSTGRES_ARCHITECTURE.md) — schema + database design.
- **API docs** — FastAPI auto-generates OpenAPI at `GET /docs` (Swagger UI) and
  `/openapi.json`; the web app consumes types from the same schema. Always
  accurate, never hand-maintained.

## Security
- [security/TENANCY_ENFORCEMENT.md](../security/TENANCY_ENFORCEMENT.md) — the app-layer tenant-isolation decision + CI guard.
- [security/SECRETS.md](../security/SECRETS.md) — secret inventory + rotation runbook.
- [security/P1_HARDENING_REPORT.md](../security/P1_HARDENING_REPORT.md), [security/PHASE_S_REPORT.md](../security/PHASE_S_REPORT.md) — hardening history.

## Product & roadmap
- [product/ROADMAP.md](../product/ROADMAP.md) — future roadmap.
- [product/CREATIVE_STUDIO_ARCHITECTURE.md](../product/CREATIVE_STUDIO_ARCHITECTURE.md) — Creative Studio (dark-launched).

## Quick reference — customer onboarding
The **customer** onboarding is in-product, not a doc: sign up (Clerk) → the
onboarding wizard creates the org + brand + owner membership in one transaction
→ dashboard. See the "Onboarding wizard" section in [/CLAUDE.md](../../CLAUDE.md).

## Admin quick actions
- Enable object storage: [object-storage.md](object-storage.md) → set `MEDIA_BACKEND=r2` + creds.
- Enable a dark feature: set its flag (see ENVIRONMENT.md → Feature flags) on both Render and Vercel where applicable.
- Rotate a secret: [security/SECRETS.md](../security/SECRETS.md).
- Investigate an incident: OPERATIONS.md → Troubleshooting; filter logs by `X-Request-Id` / `organization_id`.
- Restore data: [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md).
