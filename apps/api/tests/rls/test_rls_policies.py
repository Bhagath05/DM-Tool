"""RLS readiness tests.

Two layers:

1. **Pure-function** tests (no DB) — always run. Cover the policy-DDL
   builders, the feature-flag default, and the no-op behavior of the
   runtime GUC helpers when the flag is off.

2. **Live-Postgres** tests — skipped when PG is unreachable. Prove the
   ACTUAL enforcement semantics required by the task:
     - tenant A cannot read tenant B's rows
     - cross-tenant WRITE is blocked (WITH CHECK)
     - a service account (bypass) sees everything
     - fail-closed: no tenant context + no bypass → zero rows
     - the real policies created by migration 0032 are installed

   The live tests run as a throwaway NON-superuser role on a TEMP table
   that mirrors the exact org-scoped predicate from `aicmo.db.rls`. This
   is required because the `aicmo` admin role is a superuser, and
   superusers bypass RLS unconditionally — so testing enforcement
   demands a non-superuser role (which is what the app role must be in
   production). Everything is dropped at teardown; the shared app tables
   are never touched.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.db import rls
from tests._dbtest import admin_dsn, sync_dsn

# ---------------------------------------------------------------------
#  1. Pure-function tests (no DB)
# ---------------------------------------------------------------------


def test_flag_defaults_off():
    from aicmo.config import Settings

    assert Settings().db_rls_enabled is False


def test_rls_tables_cover_the_six_required():
    # The original 6 tenant boundaries must always be covered.
    required = {
        "organizations",
        "users",
        "leads",
        "campaign_plans",   # "campaigns"
        "generated_content",
        "audit_events",
    }
    assert required <= set(rls.RLS_TABLES)


def test_rls_tables_cover_creative_core():
    # Creative Platform core + video subsystem tenant tables (V0) are
    # registered for RLS (dormant until activated). creative_format is a
    # non-tenant catalog and is intentionally excluded.
    creative = {
        "creative_project",
        "creative_asset",
        "creative_variant",
        "creative_cost_event",
        "brand_kit",
        "creative_template",
        "creative_export",
        "video_scene",
        "video_render",
    }
    assert creative <= set(rls.RLS_TABLES)
    assert "creative_format" not in rls.RLS_TABLES


def test_org_scoped_predicate_keys_on_org_and_allows_bypass():
    pred = rls.policy_predicate("leads")
    assert "organization_id = app_current_org()" in pred
    assert "app_rls_bypassed()" in pred


def test_users_predicate_is_identity_plus_shared_org():
    pred = rls.policy_predicate("users")
    assert "id = app_current_user()" in pred
    assert "organization_members" in pred  # shared-org membership check


def test_create_then_drop_policy_sql_round_trip():
    create = rls.create_policy_sql("leads")
    drop = rls.drop_policy_sql("leads")
    # idempotent create (drops first), and the names line up.
    assert "DROP POLICY IF EXISTS rls_tenant_isolation_leads ON leads" in create
    assert "CREATE POLICY rls_tenant_isolation_leads ON leads" in create
    assert drop == "DROP POLICY IF EXISTS rls_tenant_isolation_leads ON leads;"


def test_enable_disable_sql_are_inverses():
    en = rls.enable_sql("leads")
    dis = rls.disable_sql("leads")
    assert "ENABLE ROW LEVEL SECURITY" in en and "FORCE ROW LEVEL SECURITY" in en
    assert "NO FORCE ROW LEVEL SECURITY" in dis and "DISABLE ROW LEVEL SECURITY" in dis


def test_unknown_table_raises():
    with pytest.raises(ValueError):
        rls.policy_predicate("not_a_real_table")


@pytest.mark.asyncio
async def test_runtime_helpers_are_noop_when_flag_off(monkeypatch):
    """With the flag off (default), the resolver helpers must NOT touch
    the session — otherwise the stubbed-session unit tests would break
    and prod behavior would change."""
    from aicmo.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DB_RLS_ENABLED", "false")
    get_settings.cache_clear()

    class _ExplodingSession:
        async def execute(self, *a, **k):  # pragma: no cover - must not run
            raise AssertionError("session.execute called while RLS flag off")

    s = _ExplodingSession()
    await rls.set_bypass(s, on=True)
    await rls.set_request_context(
        s, organization_id=uuid.uuid4(), user_uuid=uuid.uuid4()
    )
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_runtime_helpers_emit_set_config_when_flag_on(monkeypatch):
    from aicmo.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DB_RLS_ENABLED", "true")
    get_settings.cache_clear()

    calls: list[str] = []

    class _RecordingSession:
        async def execute(self, stmt, params=None):
            calls.append(str(stmt))

    s = _RecordingSession()
    await rls.set_bypass(s, on=True)
    await rls.set_request_context(
        s, organization_id=uuid.uuid4(), user_uuid=uuid.uuid4()
    )
    joined = " ".join(calls)
    assert "set_config" in joined
    assert "app.current_org_id" in joined
    get_settings.cache_clear()


# ---------------------------------------------------------------------
#  2. Live-Postgres enforcement tests
# ---------------------------------------------------------------------

_DSN = sync_dsn()
_ADMIN_DSN = admin_dsn()
_TEST_ROLE = "rls_probe_app_role"


def _connect_or_skip(dsn: str):
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(dsn, connect_timeout=3)
    except Exception:
        pytest.skip("Postgres not reachable")
    conn.autocommit = True
    return conn


def _pg_or_skip():
    return _connect_or_skip(_DSN)


def _set_org(cur, org_id: str | None):
    cur.execute("SELECT set_config('app.current_org_id', %s, false)", (org_id or "",))


def _set_bypass(cur, on: bool):
    cur.execute(
        "SELECT set_config('app.rls_bypass', %s, false)", ("on" if on else "off",)
    )


@pytest.fixture()
def rls_probe():
    """A throwaway NON-superuser role + TEMP table with the production org-scoped
    policy, RLS enabled + FORCEd. Yields (app_cursor, org_a, org_b).

    Privilege boundary (the point of this fixture): the throwaway role must be
    non-superuser so RLS genuinely applies, but CREATE/DROP ROLE is privileged.
    So the role lifecycle (CREATE / GRANT / DROP) runs on a DEDICATED
    administrative connection (``admin_dsn()``), while the RLS enforcement probe
    runs on the ordinary APP connection (``sync_dsn()`` — the non-superuser
    ``aicmo`` role in production-shaped setups) via ``SET ROLE``. The app role is
    never granted elevated privileges. Where the app role is already an admin
    (e.g. the CI Postgres superuser) both DSNs resolve to the same connection and
    behaviour is unchanged. Everything is torn down: the temp table dies with the
    session and the throwaway role is revoked + dropped."""
    from psycopg import sql

    admin = _connect_or_skip(_ADMIN_DSN)
    app = _pg_or_skip()
    acur, cur = admin.cursor(), app.cursor()
    role = sql.Identifier(_TEST_ROLE)
    app_user = sql.Identifier(app.info.user)  # the login role the probe runs as
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())

    # --- privileged role lifecycle on the ADMINISTRATIVE connection only ---
    # Clean slate (global object — idempotent), then allow the app connection to
    # assume the throwaway role so the probe can run as a guaranteed non-superuser.
    acur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(role))
    acur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))
    acur.execute(sql.SQL("GRANT {} TO {}").format(role, app_user))

    try:
        # --- everything below runs on the APP connection AS the throwaway
        #     non-superuser role, so RLS actually applies (superusers bypass it) ---
        cur.execute(sql.SQL("SET ROLE {}").format(role))
        cur.execute(
            "CREATE TEMP TABLE rls_probe ("
            "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  organization_id uuid NOT NULL,"
            "  label text)"
        )
        # Exact production predicate for an org-scoped table.
        pred = rls.policy_predicate("leads")
        cur.execute(
            f"CREATE POLICY p_probe ON rls_probe USING {pred} WITH CHECK {pred}"
        )
        cur.execute("ALTER TABLE rls_probe ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE rls_probe FORCE ROW LEVEL SECURITY")

        # Seed one row per org, under bypass.
        _set_bypass(cur, True)
        cur.execute(
            "INSERT INTO rls_probe (organization_id, label) VALUES (%s,'A1'),(%s,'B1')",
            (org_a, org_b),
        )
        _set_bypass(cur, False)
        _set_org(cur, None)

        yield cur, org_a, org_b
    finally:
        # App side: drop the probe-owned temp table (still SET ROLE'd), then reset
        # and close — the temp table dies with the session regardless.
        try:
            cur.execute("DROP TABLE IF EXISTS rls_probe")
            cur.execute("RESET ROLE")
        except Exception:
            pass
        app.close()
        # Admin side: revoke membership + drop the throwaway role.
        for stmt in (
            sql.SQL("REVOKE {} FROM {}").format(role, app_user),
            sql.SQL("DROP ROLE IF EXISTS {}").format(role),
        ):
            try:
                acur.execute(stmt)
            except Exception:
                pass
        admin.close()


def test_tenant_a_cannot_read_tenant_b(rls_probe):
    cur, org_a, org_b = rls_probe
    _set_org(cur, org_a)
    cur.execute("SELECT label FROM rls_probe")
    rows = {r[0] for r in cur.fetchall()}
    assert rows == {"A1"}, f"tenant A leaked rows: {rows}"

    _set_org(cur, org_b)
    cur.execute("SELECT label FROM rls_probe")
    rows = {r[0] for r in cur.fetchall()}
    assert rows == {"B1"}, f"tenant B leaked rows: {rows}"


def test_fail_closed_without_context(rls_probe):
    """No org GUC + no bypass → zero rows. RLS fails closed."""
    cur, _a, _b = rls_probe
    _set_org(cur, None)
    _set_bypass(cur, False)
    cur.execute("SELECT count(*) FROM rls_probe")
    assert cur.fetchone()[0] == 0


def test_service_account_bypass_sees_everything(rls_probe):
    cur, _a, _b = rls_probe
    _set_org(cur, None)
    _set_bypass(cur, True)
    cur.execute("SELECT count(*) FROM rls_probe")
    assert cur.fetchone()[0] == 2
    _set_bypass(cur, False)


def test_cross_tenant_write_is_blocked(rls_probe):
    """WITH CHECK: with org A active, inserting an org B row is rejected."""
    import psycopg

    cur, org_a, org_b = rls_probe
    _set_org(cur, org_a)
    _set_bypass(cur, False)
    with pytest.raises(psycopg.errors.Error):
        cur.execute(
            "INSERT INTO rls_probe (organization_id, label) VALUES (%s,'evil')",
            (org_b,),
        )


def test_real_policies_installed_by_migration():
    """Migration 0032 must have installed all six real policies."""
    conn = _pg_or_skip()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT tablename FROM pg_policies "
            "WHERE policyname LIKE 'rls_tenant_isolation_%'"
        )
        tables = {r[0] for r in cur.fetchall()}
        for t in rls.RLS_TABLES:
            assert t in tables, f"missing RLS policy on {t} (run migration 0032)"
    finally:
        conn.close()


def test_real_tables_not_yet_enforced():
    """Readiness invariant: the policies exist but RLS must remain
    DORMANT (not enabled) until activation is a deliberate ops action."""
    conn = _pg_or_skip()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT relname FROM pg_class "
            "WHERE relrowsecurity = true AND relname = ANY(%s)",
            (list(rls.RLS_TABLES),),
        )
        enforced = {r[0] for r in cur.fetchall()}
        assert enforced == set(), (
            f"RLS unexpectedly ENFORCED on {enforced} — readiness state should be "
            "dormant. Did someone run scripts/rls_activate.py?"
        )
    finally:
        conn.close()
