# Backup & Disaster Recovery

What can be lost, what protects it, and how to recover. The **only** stateful
store that holds customer data is **Postgres**. Everything else is either
derivable, ephemeral, or an external system of record.

## Data inventory & criticality

| Store | Holds | Criticality | Recovery source |
|---|---|---|---|
| **Postgres** | Users, orgs, brands, memberships, roles, leads, content/ads/visual metadata, scheduled posts + publish events, business profiles, encrypted OAuth tokens, audit logs | **Critical** | Managed backups (below) |
| **Redis** | Arq job queue (in-flight jobs) | Low | Rebuilds; `maxmemoryPolicy: noeviction` avoids dropping queued jobs. Loss = re-run of due jobs. |
| **Object storage** (R2/S3, once enabled) | Rendered images/videos | Medium | Regeneratable from the design/brief in Postgres; back up the bucket if regeneration cost matters. |
| **Local media dir** | Dev/staging renders only | None | Never used in production (safety gate). |
| **Clerk** | Auth identities, sessions | Critical (external) | Clerk is the SoR; no local backup needed. |
| **Stripe** (if enabled) | Payments/subscriptions | Critical (external) | Stripe is the SoR. |

## Backup strategy (Postgres)

- **Managed backups**: use the Render Postgres plan's automated daily backups +
  point-in-time recovery (available on paid plans — **required for production**;
  the free tier has no PITR). Verify the retention window meets your RPO.
- **Recommended posture**: RPO ≤ 24h (daily) with PITR for finer recovery; RTO
  ≤ 1h.
- **Off-platform copy** (defence against provider-account loss): schedule a
  periodic `pg_dump` to an independent bucket:
  ```bash
  pg_dump "$DATABASE_URL" --format=custom --no-owner --file=dmtool-$(date +%F).dump
  # then upload the .dump to an external bucket (R2/S3) with lifecycle retention
  ```
- **Encryption**: OAuth tokens are already Fernet-encrypted at rest, so a dump
  never contains plaintext platform tokens. Store dumps encrypted regardless.
- **Test restores quarterly** — an untested backup is not a backup.

## Restore procedure

1. **Provision** a fresh Postgres (or use Render PITR to a timestamp).
2. If restoring from a dump:
   ```bash
   pg_restore --no-owner --clean --if-exists --dbname="$NEW_DATABASE_URL" dmtool-YYYY-MM-DD.dump
   ```
3. Point `DATABASE_URL` at the restored DB and redeploy the backend. `start.sh`
   runs `alembic upgrade head` — a no-op if the dump is already at head, or it
   applies any newer migrations.
4. **Verify**: `/readyz` = 200; sign in; confirm a known org's data is present;
   check row counts on `users` / `organizations` / `leads`.
5. Rotate `INTEGRATION_TOKEN_KEY` **only** if it may have been compromised —
   rotating it makes existing encrypted OAuth tokens undecryptable (users must
   reconnect). Otherwise keep the same key so tokens keep working.

## Disaster scenarios

| Scenario | Impact | Action |
|---|---|---|
| Bad deploy / regression | App broken, data intact | Roll back frontend (Vercel) + backend (Render) — see [DEPLOYMENT.md](DEPLOYMENT.md#rollback). |
| Bad migration | Schema wrong | Fix forward with a new migration; if data-destructive, PITR to just before the deploy. |
| DB corruption / accidental delete | Data loss | PITR to just before the event, or restore latest dump; accept RPO gap. |
| Render region/provider outage | Downtime | Restore the latest off-platform dump to a new Postgres on another provider; repoint `DATABASE_URL`; redeploy. |
| Redis loss | Queued jobs lost | Non-critical; the publish cron re-picks due scheduled posts on its next run. |
| Object-storage loss (post-enable) | Rendered files gone | Re-render from the persisted design/brief, or restore the bucket backup. |
| Secret leak (`INTEGRATION_TOKEN_KEY`, Clerk, Stripe) | Token/credential exposure | Rotate per [SECRETS.md](../security/SECRETS.md); reconnect providers if the token key rotates. |

## RPO / RTO summary

- **RPO** (max data loss): ≤ 24h with daily backups; near-zero with PITR.
- **RTO** (time to restore): ≤ 1h — provision DB + repoint `DATABASE_URL` +
  redeploy (migrations auto-run).
- Redis/object-storage losses do **not** count against the data RPO (derivable).
