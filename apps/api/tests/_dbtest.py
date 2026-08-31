"""Shared endpoint + reachability helpers for the live-Postgres integration
tests (billing_live, creative_v0, cs6_video).

Two deliberate properties, neither of which changes assertions or test logic:

1. **Env-overridable endpoint.** The DSN defaults to the original dev value
   (``aicmo:aicmo@localhost:5432/aicmo``), so existing setups are unchanged,
   but ``TEST_DATABASE_URL`` lets the same tests run against any local/CI
   Postgres.

2. **Real connect+auth probe.** ``pg_reachable()`` actually connects (and
   authenticates), not just opens a socket. A *foreign* Postgres squatting on
   the port therefore makes these tests SKIP (their intent when the project
   DB is absent) instead of ERRORing on an auth failure.
"""

from __future__ import annotations

import os

_DEFAULT_ASYNC_DSN = "postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo"


def async_dsn() -> str:
    """Async (SQLAlchemy + psycopg) DSN — override via ``TEST_DATABASE_URL``."""
    return os.environ.get("TEST_DATABASE_URL", _DEFAULT_ASYNC_DSN)


def sync_dsn() -> str:
    """Sync (plain psycopg) form of :func:`async_dsn`."""
    return async_dsn().replace("+psycopg", "", 1)


def pg_reachable() -> bool:
    """True only if we can open AND authenticate a connection to the test DB."""
    try:
        import psycopg

        with psycopg.connect(sync_dsn(), connect_timeout=3):
            return True
    except Exception:
        return False
