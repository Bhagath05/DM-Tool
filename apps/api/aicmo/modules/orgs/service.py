"""Organizations + memberships service.

Public surface:

    create_organization(...)         — atomic: org + brand + member + owner role
    list_user_orgs(user_id)          — orgs the user belongs to
    get_org(org_id)                  — single org
    update_org(...)                  — rename
    archive_org(...)                 — soft delete
    list_members(org_id)             — team page
    update_member_roles(...)         — replace role set wholesale
    assign_role_to_member(...)       — add one role
    remove_role_from_member(...)     — remove one role
    remove_member(...)               — soft remove (sets status='removed')

Every mutation calls audit.record() before returning.
"""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Iterable

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.brands.models import Brand
from aicmo.modules.orgs.models import MemberRole, Organization, OrganizationMember
from aicmo.modules.orgs.schemas import (
    MemberResponse,
    OnboardingWorkspacePayload,
    OnboardingWorkspaceResult,
    OrganizationAnalytics,
    OrganizationCreate,
    OrganizationCreateResult,
    OrganizationProfileRead,
    OrganizationProfileUpdate,
    OrganizationResetResult,
    OrganizationResponse,
    OrganizationUpdate,
)
from aicmo.modules.rbac.models import Role
from aicmo.modules.users.models import User
from aicmo.tenancy.exceptions import NotAuthorized
from aicmo.tenancy.permissions import (
    compute_permissions_for_member,
    compute_role_slugs_for_member,
)

log = structlog.get_logger()


_SLUG_RX = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RX.sub("-", name.lower()).strip("-")
    base = base[:32] or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


# ---------------------------------------------------------------------
#  Create org (the headline transactional operation)
# ---------------------------------------------------------------------


async def create_organization(
    session: AsyncSession,
    *,
    actor_user: User,
    payload: OrganizationCreate,
) -> OrganizationCreateResult:
    """Atomic: User + Organization + Brand + OrganizationMember +
    MemberRole(Owner) all in one transaction.

    Caller is the actor → they become the owner. The org's first brand
    is auto-created (named after the org, or per the request).
    """
    org_name = payload.name.strip()
    brand_name = (payload.brand_name or org_name).strip()
    slug = payload.slug or _slugify(org_name)

    # 1. Organization
    org = Organization(
        slug=slug,
        name=org_name,
        owner_user_id=actor_user.id,
        status="active",
        member_count=1,
        brand_count=1,
    )
    session.add(org)
    await session.flush()

    # 2. Brand (slug 'default' is the convention for the first brand;
    # subsequent brands get _slugify(brand_name))
    brand = Brand(
        organization_id=org.id,
        slug="default",
        name=brand_name,
        status="active",
        created_by_user_id=actor_user.id,
    )
    session.add(brand)
    await session.flush()

    # 3. Membership
    member = OrganizationMember(
        organization_id=org.id,
        user_id=actor_user.id,
        last_active_brand_id=brand.id,
        status="active",
    )
    session.add(member)
    await session.flush()

    # 4. Owner role assignment — resolve the system Owner role id.
    owner_role_id = (
        await session.execute(
            select(Role.id).where(
                Role.slug == "owner",
                Role.is_system.is_(True),
            )
        )
    ).scalar_one()
    session.add(
        MemberRole(
            member_id=member.id,
            role_id=owner_role_id,
            assigned_by_user_id=actor_user.id,
        )
    )
    await session.flush()

    # 5. Audit — two events: org.created + brand.created
    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user.id,
        action="organization.created",
        target_type="organization",
        target_id=org.id,
        after={"slug": org.slug, "name": org.name},
    )
    await audit_service.record(
        session,
        organization_id=org.id,
        brand_id=brand.id,
        actor_user_id=actor_user.id,
        action="brand.created",
        target_type="brand",
        target_id=brand.id,
        after={"slug": brand.slug, "name": brand.name},
    )
    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user.id,
        action="member.role_assigned",
        target_type="member",
        target_id=member.id,
        after={"role_slug": "owner"},
    )

    return OrganizationCreateResult(
        organization=OrganizationResponse.model_validate(org),
        brand_id=brand.id,
        brand_slug=brand.slug,
        member_id=member.id,
    )


# ---------------------------------------------------------------------
#  Onboarding wizard — W1-15
# ---------------------------------------------------------------------


async def create_workspace(
    session: AsyncSession,
    *,
    actor_user: User,
    payload: OnboardingWorkspacePayload,
) -> OnboardingWorkspaceResult:
    """Transactional create-everything for the onboarding wizard.

    Differs from `create_organization` in three ways:
      1. Both slugs (org + brand) are user-controlled — wizard step 1/2.
      2. Optionally updates the caller's `display_name` from step 3.
      3. Returns a dense payload tuned for immediate frontend hydration.

    Failure modes:
      - Duplicate organization_slug → IntegrityError → caller catches
        and returns 409. We re-raise as HTTPException for a clean API.
      - Duplicate brand_slug within the new org → can't happen here
        (we're creating the first brand) but the partial unique index
        protects us if invariants ever drift.

    The whole sequence happens inside ONE transaction (controlled by the
    route's `session` dep, which commits after this returns or rolls
    back on exception).
    """
    from sqlalchemy.exc import IntegrityError

    from aicmo.db import rls as _rls

    # RLS readiness — this runs PRE-tenant (it CREATES the org), so RLS
    # policies on `organizations`/`users` would block the inserts. Bypass
    # for this transaction. No-op when DB_RLS_ENABLED is false.
    await _rls.set_bypass(session, on=True)

    org_name = payload.organization_name.strip()
    org_slug = payload.organization_slug.strip().lower()
    brand_name = payload.brand_name.strip()
    brand_slug = payload.brand_slug.strip().lower()

    # 0. Optionally update display_name. Done first so it's part of the
    # same TX — a downstream failure rolls back this rename too.
    if payload.display_name is not None:
        new_dn = payload.display_name.strip()
        if new_dn and new_dn != actor_user.display_name:
            actor_user.display_name = new_dn

    # 1. Organization
    org = Organization(
        slug=org_slug,
        name=org_name,
        owner_user_id=actor_user.id,
        status="active",
        member_count=1,
        brand_count=1,
    )
    session.add(org)
    try:
        await session.flush()
    except IntegrityError as e:
        # Duplicate org slug — convert to 409 for a clean wizard error.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Organization slug '{org_slug}' is already taken. Pick another.",
        ) from e

    # 2. Brand
    brand = Brand(
        organization_id=org.id,
        slug=brand_slug,
        name=brand_name,
        status="active",
        created_by_user_id=actor_user.id,
    )
    session.add(brand)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Brand slug '{brand_slug}' is already taken in this org.",
        ) from e

    # 3. Membership
    member = OrganizationMember(
        organization_id=org.id,
        user_id=actor_user.id,
        last_active_brand_id=brand.id,
        status="active",
    )
    session.add(member)
    await session.flush()

    # 4. Owner role — resolve system role id
    owner_role_id = (
        await session.execute(
            select(Role.id).where(
                Role.slug == "owner",
                Role.is_system.is_(True),
            )
        )
    ).scalar_one()
    session.add(
        MemberRole(
            member_id=member.id,
            role_id=owner_role_id,
            assigned_by_user_id=actor_user.id,
        )
    )
    await session.flush()

    # 5. Audit trail — three events so the team page later shows who
    # bootstrapped what.
    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user.id,
        action="organization.created",
        target_type="organization",
        target_id=org.id,
        after={"slug": org.slug, "name": org.name, "via": "onboarding_wizard"},
    )
    await audit_service.record(
        session,
        organization_id=org.id,
        brand_id=brand.id,
        actor_user_id=actor_user.id,
        action="brand.created",
        target_type="brand",
        target_id=brand.id,
        after={"slug": brand.slug, "name": brand.name, "via": "onboarding_wizard"},
    )
    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user.id,
        action="member.role_assigned",
        target_type="member",
        target_id=member.id,
        after={"role_slug": "owner", "via": "onboarding_wizard"},
    )

    # 6. A4 — optionally INSERT BusinessProfile in the SAME transaction.
    # Only when the wizard collected enough data to make a meaningful
    # profile. If any required-for-profile field is missing/blank, skip
    # quietly — user can complete it later via /api/v1/business/onboarding.
    profile_created = await _maybe_create_business_profile(
        session,
        payload=payload,
        actor_user=actor_user,
        organization_id=org.id,
        brand_id=brand.id,
    )

    log.info(
        "onboarding.workspace_created",
        org_id=str(org.id),
        org_slug=org.slug,
        brand_id=str(brand.id),
        brand_slug=brand.slug,
        user_uuid=str(actor_user.id),
        business_profile_created=profile_created,
    )

    return OnboardingWorkspaceResult(
        organization_id=org.id,
        organization_slug=org.slug,
        organization_name=org.name,
        brand_id=brand.id,
        brand_slug=brand.slug,
        brand_name=brand.name,
        member_id=member.id,
        role_slugs=["owner"],
    )


async def _maybe_create_business_profile(
    session: AsyncSession,
    *,
    payload: OnboardingWorkspacePayload,
    actor_user: User,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> bool:
    """Create a BusinessProfile in the current TX if the payload carries
    enough data. Returns True iff a profile was created.

    Required-for-profile floor (mirrors `BusinessProfileBase`'s required
    fields without re-importing them — keeping this service decoupled
    from the onboarding module's internal validators):
      - industry (non-empty)
      - target_audience (>= 10 chars — matches BusinessProfileBase floor)
      - brand_tone (non-empty)
      - primary_goal (non-empty)
      - at least one preferred_platform

    If any are missing, return False without raising. The wizard's UI
    decides what to require strictly; this server-side gate is generous
    so a partial payload doesn't 422 the whole workspace create.
    """
    industry = (payload.industry or "").strip()
    target_audience = (payload.target_audience or "").strip()
    brand_tone = (payload.brand_tone or "").strip()
    primary_goal = (payload.primary_goal or "").strip()
    platforms = [p.strip() for p in payload.preferred_platforms if p.strip()]

    if not industry:
        return False
    if len(target_audience) < 10:
        return False
    if not brand_tone:
        return False
    if not primary_goal:
        return False
    if not platforms:
        return False

    # Import locally so a missing onboarding module (unlikely) doesn't
    # break workspace creation at import time.
    from aicmo.modules.onboarding.models import BusinessProfile

    profile = BusinessProfile(
        id=uuid.uuid4(),
        user_id=actor_user.clerk_user_id,
        organization_id=organization_id,
        brand_id=brand_id,
        business_name=payload.organization_name.strip(),
        website=(payload.website or None),
        industry=industry,
        target_audience=target_audience,
        brand_tone=brand_tone,
        competitors=[],
        # `goals` is a list on the model; the wizard collects a single
        # primary_goal — store it as a one-item list so downstream
        # modules (trends, content) that read `goals` work uniformly.
        goals=[primary_goal],
        preferred_platforms=platforms,
        # Phase 2.0 fields stay null on wizard creates.
        business_location=None,
        current_monthly_leads_band=None,
        monthly_budget_band=None,
        primary_goal_text=primary_goal,
        # Persona segmentation (P-series). Optional — passes through
        # unchanged if absent. DB CHECK constraint (migration 0019)
        # rejects typos.
        persona=payload.persona,
        analysis_status="pending",
        analysis=None,
        analysis_error=None,
    )
    session.add(profile)
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        actor_user_id=actor_user.id,
        action="business_profile.created",
        target_type="business_profile",
        target_id=profile.id,
        after={"industry": industry, "via": "onboarding_wizard"},
    )
    return True


# ---------------------------------------------------------------------
#  Reads
# ---------------------------------------------------------------------


async def list_user_orgs(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[OrganizationResponse]:
    stmt = (
        select(Organization)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        )
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active",
            Organization.status != "deleted",
        )
        .order_by(Organization.created_at)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [OrganizationResponse.model_validate(r) for r in rows]


async def get_org(
    session: AsyncSession, *, org_id: uuid.UUID
) -> OrganizationResponse:
    row = await session.get(Organization, org_id)
    if row is None or row.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return OrganizationResponse.model_validate(row)


# ---------------------------------------------------------------------
#  Updates
# ---------------------------------------------------------------------


async def update_org(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
) -> OrganizationResponse:
    org = await session.get(Organization, org_id)
    if org is None or org.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    before = {"name": org.name}
    if payload.name is not None and payload.name.strip() != org.name:
        org.name = payload.name.strip()
    after = {"name": org.name}
    await session.flush()

    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user_id,
        action="organization.updated",
        target_type="organization",
        target_id=org.id,
        before=before,
        after=after,
    )
    return OrganizationResponse.model_validate(org)


async def archive_org(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> OrganizationResponse:
    org = await session.get(Organization, org_id)
    if org is None or org.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    org.status = "deleted"
    await session.flush()
    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user_id,
        action="organization.deleted",
        target_type="organization",
        target_id=org.id,
    )
    return OrganizationResponse.model_validate(org)


# ---------------------------------------------------------------------
#  Danger zone — reset & purge
# ---------------------------------------------------------------------
#
# `reset_organization_data` clears every USER-PROVIDED row for the org
# while keeping the workspace shell. The preserve set below is the small
# list of tables that survive a reset; everything else carrying an
# `organization_id` column is wiped. Driven off the LIVE schema so a new
# content table is cleared automatically — no maintenance when modules
# add tables.
#
# `purge_organization` is the irreversible hard delete: drop the org row
# and let ON DELETE CASCADE (167 FKs) remove the rest.

RESET_PRESERVE_TABLES: frozenset[str] = frozenset(
    {
        # identity / RBAC / structure — the workspace itself survives
        "organizations",
        "organization_members",
        "organization_invite",
        "roles",
        "brands",
        # billing history & external connections — not "content the
        # user provides"; wiping these would force re-auth / lose invoices
        "subscription",
        "invoice",
        "usage_event",
        "stripe_event",
        "billing_upgrade_request",
        "integration_connection",
        "social_connections",
        "connector_metrics",
        "connector_sync_runs",
        "notification_preference",
        # audit / security trail — keep so the reset stays auditable
        "audit_events",
        "ai_audit_events",
        "security_event",
    }
)


async def member_is_owner(
    session: AsyncSession, member_id: uuid.UUID | None
) -> bool:
    """Public guard: does this membership hold the system Owner role?

    Used by the router to gate the destructive reset/purge endpoints to
    org owners only (RBAC `organization.manage` is also held by admins).
    """
    if member_id is None:
        return False
    return await _is_owner(session, member_id)


async def reset_organization_data(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> OrganizationResetResult:
    """Wipe all USER-PROVIDED content for `org_id`, keeping the workspace
    shell (org + members + roles + brands + billing + connections).

    Deletes the business profile and every generated / derived asset
    (campaigns, content, leads, creatives, videos, social posts, trend
    reports, performance data, learning events, bundles, …). The set is
    computed from the live schema: every table with an `organization_id`
    column MINUS `RESET_PRESERVE_TABLES`.

    FK-safe without a hardcoded delete order: each table delete runs in
    its own SAVEPOINT; one that trips a not-yet-satisfied FK is retried
    on a later pass. Converges because the content FK graph is acyclic.
    Refuses (409) rather than leaving the workspace half-cleared if a
    table can't be drained.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from aicmo.db import rls as _rls

    org = await session.get(Organization, org_id)
    if org is None or org.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    # We delete across many tenant tables; RLS would scope each delete to
    # the GUC tenant. Bypass so we operate on exactly org_id. No-op when
    # DB_RLS_ENABLED is false.
    await _rls.set_bypass(session, on=True)

    rows = (
        await session.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND column_name = 'organization_id'"
            )
        )
    ).all()
    targets = sorted({r[0] for r in rows} - RESET_PRESERVE_TABLES)

    details: dict[str, int] = {}
    remaining = list(targets)
    # Worst case: one table drains per pass → at most len(targets) passes.
    for _pass in range(len(targets) + 1):
        if not remaining:
            break
        still: list[str] = []
        progressed = False
        for tbl in remaining:
            try:
                async with session.begin_nested():
                    res = await session.execute(
                        text(
                            f'DELETE FROM "{tbl}" '
                            "WHERE organization_id = :oid"
                        ),
                        {"oid": str(org_id)},
                    )
                    deleted = int(res.rowcount or 0)
            except IntegrityError:
                # Blocked by a child row in a table we haven't drained
                # yet — retry on the next pass.
                still.append(tbl)
                continue
            details[tbl] = deleted
            progressed = True
        remaining = still
        if not progressed:
            break

    if remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Could not fully clear workspace data; blocked tables: "
            + ", ".join(remaining),
        )

    cleared = {t: n for t, n in details.items() if n > 0}
    rows_deleted = sum(cleared.values())

    await audit_service.record(
        session,
        organization_id=org.id,
        actor_user_id=actor_user_id,
        action="organization.reset",
        target_type="organization",
        target_id=org.id,
        after={
            "tables_cleared": len(cleared),
            "rows_deleted": rows_deleted,
        },
    )
    log.warning(
        "organization.reset",
        org_id=str(org.id),
        actor_user_id=str(actor_user_id),
        tables_cleared=len(cleared),
        rows_deleted=rows_deleted,
    )

    return OrganizationResetResult(
        organization_id=org.id,
        tables_cleared=len(cleared),
        rows_deleted=rows_deleted,
        details=cleared,
    )


async def purge_organization(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """HARD delete — remove the org row so ON DELETE CASCADE drops every
    tenant child. Irreversible. Distinct from `archive_org` (soft,
    status='deleted'). Use the raw DELETE rather than `session.delete`
    so we rely on DB-level cascade instead of loading 40+ ORM
    relationship collections.
    """
    from sqlalchemy import text

    from aicmo.db import rls as _rls

    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    await _rls.set_bypass(session, on=True)

    # Log BEFORE the delete — the audit_events rows cascade away with the
    # org, so a DB-side audit record would be pointless here. structlog
    # keeps a durable trace outside the deleted tenant.
    log.warning(
        "organization.purged",
        org_id=str(org_id),
        name=org.name,
        slug=org.slug,
        actor_user_id=str(actor_user_id),
    )
    # Evict the ORM identity-map copy so a later autoflush/commit doesn't
    # try to reconcile a row that no longer exists.
    session.expunge(org)
    await session.execute(
        text("DELETE FROM organizations WHERE id = :oid"),
        {"oid": str(org_id)},
    )


# ---------------------------------------------------------------------
#  Members
# ---------------------------------------------------------------------


async def list_members(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    include_inactive: bool = False,
) -> list[MemberResponse]:
    """Roster for the org. Default: active members only (backward
    compatible). `include_inactive=True` also returns suspended members
    so the enterprise Members page can offer reactivate — 'removed'
    members are always excluded (they've left)."""
    from aicmo.modules.security.models import UserSession

    allowed_statuses = ["active", "suspended"] if include_inactive else ["active"]
    stmt = (
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.status.in_(allowed_statuses),
        )
        .order_by(OrganizationMember.joined_at)
    )
    rows = (await session.execute(stmt)).all()
    out: list[MemberResponse] = []
    for m, u in rows:
        roles = await compute_role_slugs_for_member(session, m.id)
        last_seen = (
            await session.execute(
                select(UserSession.last_seen_at)
                .where(
                    UserSession.user_id == u.id,
                    UserSession.revoked_at.is_(None),
                )
                .order_by(UserSession.last_seen_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(
            MemberResponse(
                id=m.id,
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                role_slugs=sorted(roles),
                last_active_brand_id=m.last_active_brand_id,
                joined_at=m.joined_at,
                status=m.status,
                last_active_at=last_seen,
                is_owner="owner" in roles,
            )
        )
    return out


async def get_member(
    session: AsyncSession, *, org_id: uuid.UUID, member_id: uuid.UUID
) -> OrganizationMember:
    row = await session.get(OrganizationMember, member_id)
    if row is None or row.organization_id != org_id or row.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return row


async def _is_owner(
    session: AsyncSession, member_id: uuid.UUID
) -> bool:
    """Helper: is this member assigned the system Owner role?"""
    slugs = await compute_role_slugs_for_member(session, member_id)
    return "owner" in slugs


async def _count_owners(
    session: AsyncSession, org_id: uuid.UUID
) -> int:
    """Count active members of `org_id` who hold the system 'owner' role.

    Used by the last-owner safety check in `remove_role` — refuses to
    revoke owner if doing so would leave the org with zero owners. The
    UI surfaces `team_overview.can_revoke_owner` based on the same count.
    """
    from sqlalchemy import func as _func

    stmt = (
        select(_func.count(MemberRole.member_id.distinct()))
        .join(Role, Role.id == MemberRole.role_id)
        .join(
            OrganizationMember,
            OrganizationMember.id == MemberRole.member_id,
        )
        .where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.status == "active",
            Role.slug == "owner",
            Role.is_system.is_(True),
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


# ---------------------------------------------------------------------
#  Phase 6.6 Slice 4 — team-management (Admin) safety + escalation guards
# ---------------------------------------------------------------------

_MANAGE_PERM = "team.manage"


async def _member_can_manage_team(
    session: AsyncSession, member_id: uuid.UUID
) -> bool:
    perms = await compute_permissions_for_member(session, member_id)
    return _MANAGE_PERM in perms


async def _count_team_managers(
    session: AsyncSession, org_id: uuid.UUID
) -> int:
    """Active members who can manage the team (hold `team.manage` after
    ALLOW/DENY resolution). The 'last Admin' floor is defined against this
    — it's what actually keeps a workspace administrable."""
    members = (
        (
            await session.execute(
                select(OrganizationMember.id).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for mid in members:
        if await _member_can_manage_team(session, mid):
            count += 1
    return count


async def _max_role_priority(
    session: AsyncSession, member_id: uuid.UUID
) -> int:
    """Highest `roles.priority` the member holds. Used to stop a manager
    from granting a role that outranks their own (privilege escalation)."""
    stmt = (
        select(func.max(Role.priority))
        .join(MemberRole, MemberRole.role_id == Role.id)
        .where(MemberRole.member_id == member_id)
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def assign_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role_slug: str,
) -> list[str]:
    """Add a role assignment to a member. Returns the new role set.

    Rules (in code, not policy):
    - Admins cannot assign 'owner' (org has exactly one owner; transfer
      flow is a separate slice).
    - Admins cannot modify the org owner's roles.
    """
    member = await get_member(session, org_id=org_id, member_id=member_id)
    _ = member  # validated for 404; not otherwise used
    role = await _load_system_or_org_role(
        session, org_id=org_id, role_slug=role_slug
    )

    actor_is_owner = await _is_owner(session, actor_member_id)
    target_is_owner = await _is_owner(session, member_id)

    if role_slug == "owner" and not actor_is_owner:
        raise NotAuthorized(action="member.assign_owner", role="admin")
    if target_is_owner and not actor_is_owner:
        raise NotAuthorized(action="member.modify_owner", role="admin")

    # Privilege-escalation floor: a non-owner may not grant a role that
    # outranks their own highest role. Owners bypass (they're the top).
    if not actor_is_owner:
        actor_max = await _max_role_priority(session, actor_member_id)
        if (role.priority or 0) > actor_max:
            raise NotAuthorized(
                action="member.assign_higher_role", role="admin"
            )

    # Idempotent
    existing = (
        await session.execute(
            select(MemberRole).where(
                MemberRole.member_id == member_id,
                MemberRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            MemberRole(
                member_id=member_id,
                role_id=role.id,
                assigned_by_user_id=actor_user_id,
            )
        )
        await session.flush()
        await audit_service.record(
            session,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            action="member.role_assigned",
            target_type="member",
            target_id=member_id,
            after={"role_slug": role_slug},
        )

    return sorted(await compute_role_slugs_for_member(session, member_id))


async def remove_role(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role_slug: str,
) -> list[str]:
    """Remove a role assignment. Returns the new role set.

    Refuses to remove the last role from a member (every active member
    must hold at least one role).
    """
    member = await get_member(session, org_id=org_id, member_id=member_id)
    role = await _load_system_or_org_role(
        session, org_id=org_id, role_slug=role_slug
    )

    actor_is_owner = await _is_owner(session, actor_member_id)
    target_is_owner = await _is_owner(session, member_id)

    # Phase 10.2d — owner revocation policy:
    #   - Only an existing owner may revoke the owner role from anyone.
    #   - Even an owner cannot revoke owner if it would leave zero
    #     owners in the org (last-owner safety). This is the failsafe;
    #     the UI's `team_overview.can_revoke_owner` should never offer
    #     the affordance in that state, but server enforces regardless.
    if role_slug == "owner":
        if not actor_is_owner:
            raise NotAuthorized(action="member.remove_owner", role="admin")
        if await _count_owners(session, org_id) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot remove the last owner. Promote another member first.",
            )
    if target_is_owner and not actor_is_owner:
        raise NotAuthorized(action="member.modify_owner", role="admin")

    existing = (
        await session.execute(
            select(MemberRole).where(
                MemberRole.member_id == member_id,
                MemberRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return sorted(await compute_role_slugs_for_member(session, member_id))

    # Don't leave the member role-less.
    current_count = len(
        await compute_role_slugs_for_member(session, member_id)
    )
    if current_count <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Member must hold at least one role. Assign another role first.",
        )

    # Last-Admin floor: capture whether this removal orphans team
    # management. `get_db` discards the flush on the raise below (no
    # commit), so nothing is persisted.
    had_manage = await _member_can_manage_team(session, member_id)
    managers_before = (
        await _count_team_managers(session, org_id) if had_manage else 0
    )

    await session.delete(existing)
    await session.flush()

    if had_manage and managers_before <= 1:
        if not await _member_can_manage_team(session, member_id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot remove the last member who can manage the team. "
                "Grant another member an admin role first.",
            )

    await audit_service.record(
        session,
        organization_id=org_id,
        actor_user_id=actor_user_id,
        action="member.role_removed",
        target_type="member",
        target_id=member_id,
        before={"role_slug": role_slug},
    )
    _ = member  # silence unused
    return sorted(await compute_role_slugs_for_member(session, member_id))


async def replace_roles(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role_slugs: Iterable[str],
) -> list[str]:
    """Diff-replace: ensure member ends up with exactly the given role
    slugs. Convenient for a settings-UI dropdown that posts the full
    desired state."""
    desired = set(role_slugs)
    if not desired:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Member must hold at least one role"
        )
    current = await compute_role_slugs_for_member(session, member_id)
    to_add = desired - current
    to_remove = current - desired
    for slug in to_remove:
        await remove_role(
            session,
            actor_user_id=actor_user_id,
            actor_member_id=actor_member_id,
            org_id=org_id,
            member_id=member_id,
            role_slug=slug,
        )
    for slug in to_add:
        await assign_role(
            session,
            actor_user_id=actor_user_id,
            actor_member_id=actor_member_id,
            org_id=org_id,
            member_id=member_id,
            role_slug=slug,
        )
    return sorted(await compute_role_slugs_for_member(session, member_id))


async def remove_member(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    member_id: uuid.UUID,
) -> None:
    member = await get_member(session, org_id=org_id, member_id=member_id)

    target_is_owner = await _is_owner(session, member_id)
    actor_is_owner = await _is_owner(session, actor_member_id)
    if target_is_owner:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot remove the org owner. Transfer ownership first.",
        )
    if actor_member_id == member_id and actor_is_owner:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Owner cannot self-remove."
        )

    # Last-Admin floor — never strand a workspace with nobody who can
    # manage the team (belt-and-suspenders alongside the last-owner rule).
    if await _member_can_manage_team(session, member_id):
        if await _count_team_managers(session, org_id) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot remove the last member who can manage the team.",
            )

    member.status = "removed"
    # Decrement org member_count for fast UI.
    org = await session.get(Organization, org_id)
    if org and org.member_count > 0:
        org.member_count -= 1
    await session.flush()
    await audit_service.record(
        session,
        organization_id=org_id,
        actor_user_id=actor_user_id,
        action="member.removed",
        target_type="member",
        target_id=member_id,
    )


async def set_member_status(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    active: bool,
) -> MemberResponse:
    """Deactivate (suspend) or reactivate a member.

    A suspended member keeps their roles + history but can't act until
    reactivated. Guards mirror removal: the owner can't be deactivated,
    you can't deactivate yourself, and you can't suspend the last member
    who can manage the team.
    """
    member = await get_member_any_status(session, org_id=org_id, member_id=member_id)
    new_status = "active" if active else "suspended"
    if member.status == new_status:
        return await _member_response(session, member)

    if not active:
        if await _is_owner(session, member_id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot deactivate the org owner.",
            )
        if actor_member_id == member_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "You cannot deactivate yourself."
            )
        if await _member_can_manage_team(session, member_id):
            if await _count_team_managers(session, org_id) <= 1:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Cannot deactivate the last member who can manage the team.",
                )

    member.status = new_status
    await session.flush()
    await audit_service.record(
        session,
        organization_id=org_id,
        actor_user_id=actor_user_id,
        action="member.reactivated" if active else "member.deactivated",
        target_type="member",
        target_id=member_id,
    )
    return await _member_response(session, member)


async def transfer_ownership(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    org_id: uuid.UUID,
    new_owner_member_id: uuid.UUID,
) -> None:
    """Hand the workspace Owner role to another active member.

    Only the current owner may do this. The flow is ordered so the org is
    never left ownerless: the new owner is granted first, `owner_user_id`
    is repointed, the outgoing owner is kept on as an Admin (never
    stranded), and only then is their Owner role revoked — at which point
    two owners exist momentarily, so the last-owner guard is satisfied.
    """
    if not await _is_owner(session, actor_member_id):
        raise NotAuthorized(action="member.transfer_ownership", role="admin")
    if new_owner_member_id == actor_member_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already own this workspace."
        )
    new_owner = await get_member(
        session, org_id=org_id, member_id=new_owner_member_id
    )
    if await _is_owner(session, new_owner_member_id):
        return  # already the owner — nothing to do

    owner_role = await _load_system_or_org_role(
        session, org_id=org_id, role_slug="owner"
    )
    admin_role = await _load_system_or_org_role(
        session, org_id=org_id, role_slug="admin"
    )

    async def _has_role(member_id: uuid.UUID, role_id: uuid.UUID) -> object | None:
        return (
            await session.execute(
                select(MemberRole).where(
                    MemberRole.member_id == member_id,
                    MemberRole.role_id == role_id,
                )
            )
        ).scalar_one_or_none()

    # 1) Grant Owner to the incoming owner.
    if await _has_role(new_owner_member_id, owner_role.id) is None:
        session.add(
            MemberRole(
                member_id=new_owner_member_id,
                role_id=owner_role.id,
                assigned_by_user_id=actor_user_id,
            )
        )
    # 2) Repoint the org's canonical owner.
    org = await session.get(Organization, org_id)
    if org is not None:
        org.owner_user_id = new_owner.user_id
    await session.flush()

    # 3) Keep the outgoing owner on as an Admin so they aren't stranded.
    if await _has_role(actor_member_id, admin_role.id) is None:
        session.add(
            MemberRole(
                member_id=actor_member_id,
                role_id=admin_role.id,
                assigned_by_user_id=actor_user_id,
            )
        )
    # 4) Revoke Owner from the outgoing owner (two owners exist now → safe).
    old = await _has_role(actor_member_id, owner_role.id)
    if old is not None:
        await session.delete(old)
    await session.flush()

    await audit_service.record(
        session,
        organization_id=org_id,
        actor_user_id=actor_user_id,
        action="member.ownership_transferred",
        target_type="member",
        target_id=new_owner_member_id,
        after={"new_owner_user_id": str(new_owner.user_id)},
    )


async def get_member_any_status(
    session: AsyncSession, *, org_id: uuid.UUID, member_id: uuid.UUID
) -> OrganizationMember:
    """Like `get_member` but accepts active OR suspended (not removed) —
    needed to reactivate a suspended member."""
    row = await session.get(OrganizationMember, member_id)
    if row is None or row.organization_id != org_id or row.status == "removed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return row


async def _member_response(
    session: AsyncSession, member: OrganizationMember
) -> MemberResponse:
    user = await session.get(User, member.user_id)
    roles = await compute_role_slugs_for_member(session, member.id)
    return MemberResponse(
        id=member.id,
        user_id=member.user_id,
        email=user.email if user else "",
        display_name=user.display_name if user else None,
        avatar_url=user.avatar_url if user else None,
        role_slugs=sorted(roles),
        last_active_brand_id=member.last_active_brand_id,
        joined_at=member.joined_at,
        status=member.status,
        is_owner="owner" in roles,
    )


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


# =====================================================================
#  Phase 10.2f — Org profile + analytics
# =====================================================================
#
# Three new public functions:
#
#   get_org_profile(org_id)       → OrganizationProfileRead (incl. 10.2f
#                                   logo_url/website/industry/timezone/country)
#   update_org_profile(...)       → patch profile, audit
#   get_org_analytics(org_id)     → counts + last_activity_at, for the
#                                   Settings → Organization overview tiles
#
# Design notes:
#
#   - `update_org_profile` distinguishes "absent" from "explicit empty":
#     Pydantic exposes only `model_dump(exclude_unset=True)` to tell the
#     two apart. Empty string → NULL (consistent with the schema's null
#     semantics docstring).
#   - The `name` field is reused from `OrganizationUpdate` semantics —
#     no behaviour change beyond accepting it alongside profile fields.
#   - `get_org_analytics` joins through team.OrganizationInvite to count
#     pending invites. Last-activity is the max of audit_logs.created_at
#     and any future signal — for now we use audit_logs alone since
#     security.UserSession lives behind a Clerk sync that may be off.


async def get_org_profile(
    session: AsyncSession, *, org_id: uuid.UUID
) -> OrganizationProfileRead:
    """Extended GET for Settings → Organization. Same auth contract as
    `get_org` — `organization.manage` permission is enforced at the
    route layer."""
    row = await session.get(Organization, org_id)
    if row is None or row.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return OrganizationProfileRead.model_validate(row)


async def update_org_profile(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    org_id: uuid.UUID,
    payload: OrganizationProfileUpdate,
) -> OrganizationProfileRead:
    """PATCH name + profile fields. Empty-string → NULL (the explicit
    'clear this field' opt-in).

    Only fields the caller actually sent get touched — `exclude_unset`
    on the dump lets us distinguish 'leave alone' from 'set to None'.
    """
    org = await session.get(Organization, org_id)
    if org is None or org.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    sent = payload.model_dump(exclude_unset=True)
    before: dict[str, str | None] = {}
    after: dict[str, str | None] = {}

    def _normalise(val: str | None) -> str | None:
        # "" → NULL; otherwise strip leading/trailing whitespace
        if val is None:
            return None
        s = val.strip()
        return s or None

    # `name` is special — never NULL on org. Refuse to clear it.
    if "name" in sent:
        new_name = _normalise(sent["name"])
        if not new_name:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Organization name cannot be empty",
            )
        if new_name != org.name:
            before["name"] = org.name
            org.name = new_name
            after["name"] = new_name

    # Profile fields — all nullable.
    for field in ("logo_url", "website", "industry", "timezone", "country"):
        if field in sent:
            new_val = _normalise(sent[field])
            current = getattr(org, field)
            if new_val != current:
                before[field] = current
                setattr(org, field, new_val)
                after[field] = new_val

    if after:
        await session.flush()
        await audit_service.record(
            session,
            organization_id=org.id,
            actor_user_id=actor_user_id,
            action="organization.profile_updated",
            target_type="organization",
            target_id=org.id,
            before=before,
            after=after,
        )
    return OrganizationProfileRead.model_validate(org)


async def get_org_analytics(
    session: AsyncSession, *, org_id: uuid.UUID
) -> OrganizationAnalytics:
    """Aggregate counts for the Settings → Organization overview tiles.

    Not a metrics dashboard. Performance Intelligence (Phase 9.1.5)
    is untouched — this is purely org-shape counters.
    """
    from datetime import datetime, timezone

    from sqlalchemy import func as _func

    from aicmo.modules.audit.models import AuditEvent
    from aicmo.modules.team.models import OrganizationInvite

    org = await session.get(Organization, org_id)
    if org is None or org.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    # Brand counts — both totals (excl. deleted) and active subset.
    brand_total_stmt = select(_func.count(Brand.id)).where(
        Brand.organization_id == org_id,
        Brand.status != "deleted",
    )
    brand_active_stmt = select(_func.count(Brand.id)).where(
        Brand.organization_id == org_id,
        Brand.status == "active",
    )
    brand_count = int((await session.execute(brand_total_stmt)).scalar_one() or 0)
    active_brand_count = int(
        (await session.execute(brand_active_stmt)).scalar_one() or 0
    )

    # Member count — re-use the denormalised counter for the headline,
    # but verify against a live count so a stale counter can't silently
    # mislead the founder.
    live_member_stmt = select(_func.count(OrganizationMember.id)).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.status == "active",
    )
    member_count = int(
        (await session.execute(live_member_stmt)).scalar_one() or 0
    )

    # Pending invites — status='pending' AND not yet expired. The team
    # service marks them as 'expired' lazily; for analytics we apply
    # the time filter directly so a stale 'pending' row doesn't lie.
    now = datetime.now(timezone.utc)
    pending_invite_stmt = select(_func.count(OrganizationInvite.id)).where(
        OrganizationInvite.organization_id == org_id,
        OrganizationInvite.status == "pending",
        OrganizationInvite.expires_at > now,
    )
    pending_invite_count = int(
        (await session.execute(pending_invite_stmt)).scalar_one() or 0
    )

    # Last activity — max(audit_events.occurred_at). NULL if the org has
    # done nothing since creation (which is a useful empty-state signal).
    last_activity_stmt = select(_func.max(AuditEvent.occurred_at)).where(
        AuditEvent.organization_id == org_id,
    )
    last_activity_at = (
        await session.execute(last_activity_stmt)
    ).scalar_one_or_none()

    return OrganizationAnalytics(
        organization_id=org.id,
        brand_count=brand_count,
        active_brand_count=active_brand_count,
        member_count=member_count,
        pending_invite_count=pending_invite_count,
        created_at=org.created_at,
        last_activity_at=last_activity_at,
    )


async def _load_system_or_org_role(
    session: AsyncSession, *, org_id: uuid.UUID, role_slug: str
) -> Role:
    """Resolve a role by slug. Prefers org-scoped custom roles over
    system roles when both exist with the same slug."""
    stmt = (
        select(Role)
        .where(Role.slug == role_slug)
        .where((Role.organization_id == org_id) | (Role.organization_id.is_(None)))
        .order_by(Role.organization_id.desc().nullslast())
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Role '{role_slug}' not found"
        )
    return row
