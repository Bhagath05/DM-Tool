#!/usr/bin/env python
"""Activate Row-Level Security enforcement on the RLS tables.

This is the DELIBERATE, separate ops action that turns the dormant
policies (created by migration 0032) into enforced ones. It is NOT part
of the Alembic chain on purpose: enabling RLS is an operational decision
with a blast radius, not a schema migration.

Pre-conditions (the script checks the first two):
  1. Migration 0032 has run (policies + functions exist).
  2. DB_RLS_ENABLED=true in the app env  — otherwise the app won't set
     the per-request GUCs and every query will return zero rows.
  3. You have a verified rollback path (`rls_deactivate.py`) and a DB
     snapshot.

Idempotent: ENABLE/FORCE are safe to re-run.

Usage:
    cd apps/api
    .venv/bin/python -m scripts.rls_activate            # activate all
    .venv/bin/python -m scripts.rls_activate --dry-run  # print only
    .venv/bin/python -m scripts.rls_activate --check    # report state only
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from aicmo.config import get_settings
from aicmo.db import rls


def _dsn() -> str:
    # psycopg (sync) wants a plain libpq DSN — strip the SQLAlchemy driver.
    url = get_settings().database_url
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _policies_present(cur) -> set[str]:
    cur.execute(
        "SELECT tablename FROM pg_policies WHERE schemaname='public' "
        "AND policyname LIKE 'rls_tenant_isolation_%'"
    )
    return {r[0] for r in cur.fetchall()}


def _rls_enabled(cur) -> set[str]:
    cur.execute(
        "SELECT relname FROM pg_class WHERE relrowsecurity = true "
        "AND relname = ANY(%s)",
        (list(rls.RLS_TABLES),),
    )
    return {r[0] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Activate RLS enforcement.")
    ap.add_argument("--dry-run", action="store_true", help="print SQL, don't run")
    ap.add_argument("--check", action="store_true", help="report state, don't change")
    args = ap.parse_args()

    with psycopg.connect(_dsn(), connect_timeout=5) as conn:
        conn.autocommit = True
        cur = conn.cursor()

        present = _policies_present(cur)
        enabled = _rls_enabled(cur)

        if args.check:
            print("RLS state:")
            for t in rls.RLS_TABLES:
                pol = "policy✓" if t in present else "policy✗(run migration 0032)"
                en = "ENFORCED" if t in enabled else "dormant"
                print(f"  {t:22} {pol:30} {en}")
            print(f"\nDB_RLS_ENABLED (app flag): {get_settings().db_rls_enabled}")
            return 0

        # Guard: refuse to enforce if policies are missing.
        missing = [t for t in rls.RLS_TABLES if t not in present]
        if missing:
            print(
                "REFUSING: policies missing on "
                f"{missing}. Run `alembic upgrade head` (migration 0032) first.",
                file=sys.stderr,
            )
            return 2

        # Warn (don't block) if the app flag is off — activating without it
        # makes the app return zero rows.
        if not get_settings().db_rls_enabled:
            print(
                "WARNING: DB_RLS_ENABLED is false. The app will NOT set the "
                "per-request GUCs, so enforced RLS will hide all rows from "
                "the app. Set DB_RLS_ENABLED=true and restart BEFORE enforcing.",
                file=sys.stderr,
            )

        for table in rls.RLS_TABLES:
            ddl = rls.enable_sql(table)
            if args.dry_run:
                print(ddl)
                continue
            cur.execute(ddl)
            print(f"ENFORCED RLS on {table}")

        if not args.dry_run:
            print(
                "\nRLS is now ENFORCED. Run the acceptance test + verify the app "
                "works. To roll back: .venv/bin/python -m scripts.rls_deactivate"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
