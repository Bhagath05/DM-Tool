"""Row-Level Security (RLS) — single source of truth.

Phase DB-RLS. PostgreSQL RLS as a *second* tenant-isolation boundary on
top of the application-layer `WHERE brand_id = ?` filters. Defense in
depth for enterprise / SOC2.

This module is the ONE place that defines:
  - the GUC (session variable) names the policies read,
  - the SQL for the helper functions + policies (used by migration 0032,
    the activation scripts, AND the tests — so they can never drift),
  - the async runtime helpers the resolver calls to set per-request
    tenant context.

Design summary
--------------
- RLS is **org-level**: policies key on `organization_id = app_current_org()`.
  The organization is the tenant boundary. Brand-level scoping stays an
  application concern (the app still filters by `brand_id`). Org-level RLS
  catches the catastrophic failure mode — cross-*tenant* leakage.
- Three policy shapes:
    * org_scoped  — `organization_id = current_org`  (leads, campaign_plans,
                    generated_content, audit_events)
    * org_self    — the org row itself, visible if it's the active org OR
                    the caller is an active member  (organizations)
    * user_self   — a user row visible if it's the caller OR shares the
                    active org with the caller  (users — has no org_id)
- A `bypass` escape hatch (`app.rls_bypass = 'on'`) for legitimate
  pre-tenant / cross-tenant service paths (onboarding workspace creation,
  the resolver's own lookups, public lead capture). Set explicitly and
  transaction-locally — never left on.

Activation is a TWO-part switch, both required:
  1. `DB_RLS_ENABLED=true` (this app flag) → resolver sets the GUCs.
  2. `scripts/rls_activate.py` → `ENABLE`/`FORCE` RLS on the tables.
Neither alone changes behavior in a breaking way (policies are dormant
until enabled; GUCs are harmless until policies read them).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------
#  GUC (session-variable) names the policies read.
# ---------------------------------------------------------------------
GUC_ORG = "app.current_org_id"
GUC_USER = "app.current_user_id"
GUC_BYPASS = "app.rls_bypass"

# ---------------------------------------------------------------------
#  The six tables this readiness pass covers, with their policy shape.
# ---------------------------------------------------------------------
ORG_SCOPED_TABLES: tuple[str, ...] = (
    "leads",
    "campaign_plans",      # "campaigns"
    "generated_content",
    "audit_events",
    # Creative Platform core (V0) — all org-scoped (organization_id NOT NULL).
    "creative_project",
    "creative_asset",
    "creative_variant",
    "creative_cost_event",
    "brand_kit",
    "creative_template",
    "creative_export",
    # Video subsystem (V0).
    "video_scene",
    "video_render",
    # Creative Studio (CS1) — editable design model + outcome objective.
    "growth_objective",
    "creative_design",
    "creative_design_revision",
    "brand_asset",
    # (creative_format, objective_kind, layout_primitive are non-tenant
    #  catalogs — excluded, like `plan`.)
)
# Special shapes:
#   organizations — keyed on the row's own id + membership
#   users         — keyed on identity + shared-org membership
RLS_TABLES: tuple[str, ...] = ORG_SCOPED_TABLES + ("organizations", "users")


# ---------------------------------------------------------------------
#  Helper functions (created once). STABLE so the planner caches them.
# ---------------------------------------------------------------------
FUNCTIONS_SQL: str = """
CREATE OR REPLACE FUNCTION app_current_org() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION app_rls_bypassed() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(current_setting('app.rls_bypass', true), 'off') = 'on'
$$;
"""

DROP_FUNCTIONS_SQL: str = """
DROP FUNCTION IF EXISTS app_rls_bypassed();
DROP FUNCTION IF EXISTS app_current_user();
DROP FUNCTION IF EXISTS app_current_org();
"""


def _policy_name(table: str) -> str:
    return f"rls_tenant_isolation_{table}"


def policy_predicate(table: str) -> str:
    """The boolean USING/WITH CHECK predicate for a table.

    Always allows the explicit bypass path so service accounts and the
    bootstrap (pre-tenant) flows keep working.
    """
    if table in ORG_SCOPED_TABLES:
        return "(app_rls_bypassed() OR organization_id = app_current_org())"
    if table == "organizations":
        # Visible if it's the active org, OR the caller is an active member
        # of it (so the org-switcher's membership list still works).
        return (
            "(app_rls_bypassed() "
            "OR id = app_current_org() "
            "OR EXISTS (SELECT 1 FROM organization_members m "
            "           WHERE m.organization_id = organizations.id "
            "             AND m.user_id = app_current_user() "
            "             AND m.status = 'active'))"
        )
    if table == "users":
        # Visible if it's the caller's own row, OR the user shares the
        # active org with the caller (team listings).
        return (
            "(app_rls_bypassed() "
            "OR id = app_current_user() "
            "OR EXISTS (SELECT 1 FROM organization_members m "
            "           WHERE m.user_id = users.id "
            "             AND m.organization_id = app_current_org() "
            "             AND m.status = 'active'))"
        )
    raise ValueError(f"no RLS policy defined for table {table!r}")


def create_policy_sql(table: str) -> str:
    """DROP-then-CREATE so the migration + scripts are idempotent
    (Postgres has no CREATE POLICY IF NOT EXISTS)."""
    name = _policy_name(table)
    pred = policy_predicate(table)
    return (
        f"DROP POLICY IF EXISTS {name} ON {table};\n"
        f"CREATE POLICY {name} ON {table}\n"
        f"  USING {pred}\n"
        f"  WITH CHECK {pred};"
    )


def drop_policy_sql(table: str) -> str:
    return f"DROP POLICY IF EXISTS {_policy_name(table)} ON {table};"


def enable_sql(table: str) -> str:
    """ENABLE + FORCE so the policy applies even to the table owner
    (the app connects as the owner)."""
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"
    )


def disable_sql(table: str) -> str:
    return (
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )


# ---------------------------------------------------------------------
#  Runtime helpers — called from the request path. All no-op unless the
#  feature flag is on, so default behavior is byte-identical.
# ---------------------------------------------------------------------
def _flag_on() -> bool:
    # Imported lazily so this module has no import-time dependency on
    # settings (keeps the DDL builders usable from migrations/scripts
    # without booting the whole app).
    from aicmo.config import get_settings

    return get_settings().db_rls_enabled


async def set_request_context(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_uuid: uuid.UUID,
) -> None:
    """Set the per-request tenant GUCs (transaction-local) and turn the
    bypass OFF. Called by the resolver right before it returns the
    TenantContext, so the request handler body runs under org-scoped RLS.

    No-op when the flag is off.
    """
    if not _flag_on():
        return
    # set_config(setting, value, is_local=true) == SET LOCAL — scoped to
    # the current transaction, cleared on commit/rollback. Parameterized,
    # so no SQL injection surface.
    await session.execute(
        text(
            "SELECT set_config('app.current_org_id', :org, true), "
            "set_config('app.current_user_id', :usr, true), "
            "set_config('app.rls_bypass', 'off', true)"
        ),
        {"org": str(organization_id), "usr": str(user_uuid)},
    )


async def set_bypass(session: AsyncSession, on: bool = True) -> None:
    """Turn the RLS bypass on/off for the current transaction.

    Use `on=True` for legitimate pre-tenant / cross-tenant service paths:
      - the resolver's own lookups (before the org is known),
      - onboarding workspace creation (org created before any tenant),
      - public lead capture (org resolved from the landing page).

    No-op when the flag is off.
    """
    if not _flag_on():
        return
    await session.execute(
        text("SELECT set_config('app.rls_bypass', :v, true)"),
        {"v": "on" if on else "off"},
    )
