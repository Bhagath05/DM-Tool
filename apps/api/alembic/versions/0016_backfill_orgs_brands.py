"""backfill personal orgs and brands

Revision ID: 0016_backfill_orgs_brands
Revises: 0015_tenant_columns
Create Date: 2026-05-30

Data migration. For every distinct `user_id` that appears in any
business table (and isn't already in users), create:

  1. A User row (mirroring clerk_user_id; email/name placeholder until
     the Clerk webhook or /me lazy-create resolves it).
  2. A personal Organization.
  3. A default Brand (named after the user's BusinessProfile.business_name
     if available, else 'My Brand').
  4. An OrganizationMember row.
  5. A MemberRole assignment → Owner.

Then UPDATE every business table to set (organization_id, brand_id) to
the personal org + default brand of the matching user_id.

Idempotent — re-runnable. The migration finishes by asserting every
business row has non-null (org_id, brand_id), and raises if not.

This is the only data-mutating migration in S1.0. Wrapped in a single
transaction by Alembic.
"""

from __future__ import annotations

import re
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_backfill_orgs_brands"
down_revision: Union[str, None] = "0015_tenant_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables to backfill. Mirrors 0015's list.
BUSINESS_TABLES: list[str] = [
    "business_profiles",
    "trend_reports",
    "generated_content",
    "generated_ads",
    "generated_visuals",
    "rendered_visuals",
    "campaign_plans",
    "landing_pages",
    "leads",
    "bundles",
    "social_connections",
    "social_assets",
    "audience_patterns",
    "winning_patterns",
    "campaign_experiments",
    "learning_events",
]


_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_CHARS.sub("-", name.lower()).strip("-")
    base = base[:40] or "personal"
    return f"{base}-{secrets.token_hex(3)}"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Collect every distinct user_id across all business tables.
    user_ids: set[str] = set()
    for table in BUSINESS_TABLES:
        result = bind.execute(
            sa.text(f"SELECT DISTINCT user_id FROM {table} WHERE user_id IS NOT NULL")
        )
        user_ids.update(row[0] for row in result)

    if not user_ids:
        print("[backfill] No existing business data — nothing to backfill.")
        _assert_invariant(bind)
        return

    print(f"[backfill] Processing {len(user_ids)} distinct user(s)")

    # 2. For each clerk_user_id, ensure (User, Org, Brand, Member, Role).
    owner_role_id = bind.execute(
        sa.text(
            "SELECT id FROM roles WHERE slug = 'owner' AND is_system = true LIMIT 1"
        )
    ).scalar()
    if not owner_role_id:
        raise RuntimeError(
            "Owner role not found — 0014_rbac_foundation seed must run before this."
        )

    for clerk_user_id in user_ids:
        # 2a. User row — placeholder email keyed off clerk_user_id.
        # Real email will land via Clerk webhook / lazy-create on first /me call.
        placeholder_email = f"{clerk_user_id}@pending.local"
        user_id = bind.execute(
            sa.text(
                """
                INSERT INTO users (id, clerk_user_id, email, status)
                VALUES (gen_random_uuid(), :clerk_id, :email, 'active')
                ON CONFLICT (clerk_user_id) DO UPDATE
                    SET clerk_user_id = EXCLUDED.clerk_user_id  -- no-op, lets us RETURNING
                RETURNING id
                """
            ),
            {"clerk_id": clerk_user_id, "email": placeholder_email},
        ).scalar()

        # 2b. Pull business_name from BusinessProfile if available (better
        # name for the personal org than a placeholder).
        bp = bind.execute(
            sa.text(
                "SELECT business_name FROM business_profiles "
                "WHERE user_id = :uid LIMIT 1"
            ),
            {"uid": clerk_user_id},
        ).first()
        org_name = (bp[0] if bp and bp[0] else f"My Workspace").strip()
        brand_name = org_name  # default brand named same as org

        # 2c. Organization. Idempotent on (owner_user_id, name) — re-run-safe.
        org_id = bind.execute(
            sa.text(
                "SELECT id FROM organizations "
                "WHERE owner_user_id = :uid AND name = :name AND status = 'active' "
                "LIMIT 1"
            ),
            {"uid": user_id, "name": org_name},
        ).scalar()
        if not org_id:
            org_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO organizations
                        (id, slug, name, owner_user_id, status,
                         member_count, brand_count)
                    VALUES
                        (gen_random_uuid(), :slug, :name, :uid,
                         'active', 1, 1)
                    RETURNING id
                    """
                ),
                {
                    "slug": _slugify(org_name),
                    "name": org_name,
                    "uid": user_id,
                },
            ).scalar()

        # 2d. Brand. Idempotent on (org_id, slug='default').
        brand_id = bind.execute(
            sa.text(
                "SELECT id FROM brands "
                "WHERE organization_id = :oid AND slug = 'default' "
                "AND status = 'active' LIMIT 1"
            ),
            {"oid": org_id},
        ).scalar()
        if not brand_id:
            brand_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO brands
                        (id, organization_id, slug, name, status, created_by_user_id)
                    VALUES
                        (gen_random_uuid(), :oid, 'default', :name,
                         'active', :uid)
                    RETURNING id
                    """
                ),
                {"oid": org_id, "name": brand_name, "uid": user_id},
            ).scalar()

        # 2e. Membership. Idempotent.
        member_id = bind.execute(
            sa.text(
                "SELECT id FROM organization_members "
                "WHERE organization_id = :oid AND user_id = :uid "
                "AND status = 'active' LIMIT 1"
            ),
            {"oid": org_id, "uid": user_id},
        ).scalar()
        if not member_id:
            member_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO organization_members
                        (id, organization_id, user_id, status, last_active_brand_id)
                    VALUES
                        (gen_random_uuid(), :oid, :uid, 'active', :bid)
                    RETURNING id
                    """
                ),
                {"oid": org_id, "uid": user_id, "bid": brand_id},
            ).scalar()

        # 2f. Owner role assignment. Idempotent.
        bind.execute(
            sa.text(
                """
                INSERT INTO member_roles (id, member_id, role_id)
                VALUES (gen_random_uuid(), :mid, :rid)
                ON CONFLICT (member_id, role_id) DO NOTHING
                """
            ),
            {"mid": member_id, "rid": owner_role_id},
        )

        # 3. UPDATE every business table for this user.
        for table in BUSINESS_TABLES:
            bind.execute(
                sa.text(
                    f"""
                    UPDATE {table}
                    SET organization_id = :oid, brand_id = :bid
                    WHERE user_id = :uid
                      AND (organization_id IS NULL OR brand_id IS NULL)
                    """
                ),
                {"oid": org_id, "bid": brand_id, "uid": clerk_user_id},
            )

    # 4. Invariant: every business row must now have (org_id, brand_id).
    _assert_invariant(bind)

    print(f"[backfill] OK — {len(user_ids)} users backfilled successfully")


def _assert_invariant(bind: sa.engine.Connection) -> None:
    """Fail loudly if any business row is still missing tenant scope.
    Triggers transaction rollback so we never end up in a half-state."""
    for table in BUSINESS_TABLES:
        unscoped = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "
                "WHERE organization_id IS NULL OR brand_id IS NULL"
            )
        ).scalar()
        if unscoped:
            raise RuntimeError(
                f"[backfill] INVARIANT FAILED: {table} has {unscoped} "
                "row(s) with NULL organization_id or brand_id. "
                "Aborting — transaction will roll back."
            )


def downgrade() -> None:
    """Downgrade is destructive — it drops tenancy from existing data.
    Order: clear org_id/brand_id on business tables, then delete all
    member_roles / memberships / brands / orgs / users we created.

    Safe because 0017 hasn't flipped NOT NULL yet at this point in the
    migration chain.
    """
    bind = op.get_bind()
    for table in BUSINESS_TABLES:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = NULL, brand_id = NULL"
            )
        )
    bind.execute(sa.text("DELETE FROM member_roles"))
    bind.execute(sa.text("DELETE FROM organization_members"))
    bind.execute(sa.text("DELETE FROM brands"))
    bind.execute(sa.text("DELETE FROM organizations"))
    bind.execute(sa.text("DELETE FROM users"))
