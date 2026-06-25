# PostgreSQL backups (P0-1)

| Script | Purpose |
|---|---|
| `backup.sh` | Daily `pg_dump -Fc` → `dumps/`, prunes > `BACKUP_RETENTION_DAYS` (default 14). |
| `restore.sh <dump> [target]` | Recreate a db from a dump (refuses prod target without `RESTORE_ALLOW_PROD=1`). |
| `verify_restore.sh` | Backup → restore into scratch db → compare tables/orgs/migration → drop. Exit 0 = restorable. |

**Cron (daily backup + verify):**
```
30 2 * * *  /srv/ai-cmo/infra/backup/backup.sh        >> /var/log/aicmo-backup.log 2>&1
45 2 * * *  /srv/ai-cmo/infra/backup/verify_restore.sh >> /var/log/aicmo-backup.log 2>&1
```

**Production (managed Postgres):** set `BACKUP_CONTAINER=""` + libpq env
(`PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE`) and push `dumps/*.dump` to
object storage (S3 lifecycle for retention). Local/dev routes through the
`ai-cmo-postgres` docker container by default.
