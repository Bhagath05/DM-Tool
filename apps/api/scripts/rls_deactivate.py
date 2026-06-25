#!/usr/bin/env python
"""Deactivate Row-Level Security enforcement — the RLS rollback switch.

Disables (NO FORCE + DISABLE) RLS on every RLS table, returning the
database to the dormant-policy state. The policies + functions remain
installed (use migration 0032 downgrade to remove them entirely).

This is the fast rollback if enforced RLS causes a problem in
production: enforcement is off the moment this completes, no app deploy
required. Pair it with flipping DB_RLS_ENABLED back to false at your
leisure (the GUCs are harmless once nothing reads them).

Idempotent. Usage:
    cd apps/api
    .venv/bin/python -m scripts.rls_deactivate
    .venv/bin/python -m scripts.rls_deactivate --dry-run
"""

from __future__ import annotations

import argparse

import psycopg

from aicmo.config import get_settings
from aicmo.db import rls


def _dsn() -> str:
    url = get_settings().database_url
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Deactivate RLS enforcement (rollback).")
    ap.add_argument("--dry-run", action="store_true", help="print SQL, don't run")
    args = ap.parse_args()

    with psycopg.connect(_dsn(), connect_timeout=5) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        for table in rls.RLS_TABLES:
            ddl = rls.disable_sql(table)
            if args.dry_run:
                print(ddl)
                continue
            cur.execute(ddl)
            print(f"DISABLED RLS on {table}")
        if not args.dry_run:
            print(
                "\nRLS enforcement is OFF (policies remain installed but dormant). "
                "Set DB_RLS_ENABLED=false to also stop the app setting GUCs."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
