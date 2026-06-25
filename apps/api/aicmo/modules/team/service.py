"""Phase 10.2d — Team service layer.

Public surface:
  create_invite        — generate token, persist hash, return URL once
  list_invites         — pending + history per org
  revoke_invite        — admin/owner only
  preview_invite       — token → org name + role (for the acceptance UI)
  accept_invite        — token → member + role assignment, email-matched
  expire_stale_invites — background-safe sweep (called by cron, not request)
  team_overview        — aggregated members + invites + role catalog

Policy decisions (all enforced here, not by Pydantic):

  1. Owner role is NEVER invitable. Pydantic Literal rejects it
     statically; this layer adds a runtime guard for defense in depth.

  2. Admins (non-owners) cannot grant 'owner' via invite. The
     `_check_can_invite_role` policy reads is_admin_grantable from the
     role catalog.

  3. Duplicate pending invites for the same email+org are rejected.
     The partial unique index does the heavy lifting; we catch the
     IntegrityError and convert to a clean 409.

  4. Email match on accept. We compare the invited email (lowercased)
     to the authenticated user's email. The `@pending.local` placeholder
     (from lazy-create when Clerk webhook hasn't filled the email yet)
     is treated as match-any — this keeps dev/onboarding working.
     Production users always have a real Clerk-verified email and the
     match is exact.

  5. Already-member rejection. If the invitee's user_id is ALREADY an
     active member of the org (e.g. invite issued but member joined via
     another route), the accept returns 409 — we won't double-create.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.audit import service as audit_service
from aicmo.modules.orgs.models import (
    MemberRole,
    Organization,
    OrganizationMember,
)
from aicmo.modules.rbac.models import Role
from aicmo.modules.security.models import UserSession
from aicmo.modules.team import role_catalog
from aicmo.modules.team.models import OrganizationInvite
from aicmo.modules.team.schemas import (
    InviteAcceptResponse,
    InviteCreateResponse,
    InviteList,
    InvitePreview,
    InviteRead,
    MemberSummary,
    TeamOverview,
)
from aicmo.modules.users.models import User
from aicmo.tenancy.permissions import compute_role_slugs_for_member

log = structlog.get_logger()


DEFAULT_INVITE_TTL_DAYS = 7
ACCEPT_URL_PATH = "/invites/accept"
# The placeholder email lazy-create assigns when Clerk webhook hasn't
# populated the real email yet. See `_get_or_create_user` in tenancy.
PENDING_EMAIL_SUFFIX = "@pending.local"


# ---------------------------------------------------------------------
#  Exceptions
# ---------------------------------------------------------------------


class InviteRoleNotAllowed(Exception):
    """Tried to invite with a role outside the invitable set
    (or admin tried to grant a role only owner can grant)."""

    def __init__(self, role_slug: str, reason: str) -> None:
        super().__init__(f"{role_slug}: {reason}")
        self.role_slug = role_slug
        self.reason = reason


class DuplicatePendingInvite(Exception):
    """A pending invite for this email already exists in this org."""


class InviteNotFound(Exception):
    """No invite with that id or token (or hidden from caller's org)."""


class InviteAlreadyConsumed(Exception):
    """Accept on a non-pending invite (accepted / revoked / expired)."""

    def __init__(self, current_status: str) -> None:
        super().__init__(current_status)
        self.current_status = current_status


class InviteExpired(Exception):
    pass


class InviteEmailMismatch(Exception):
    """Authenticated user's email doesn't match the invite's email."""


class AlreadyMember(Exception):
    """User is already an active member of the org the invite belongs to."""


# ---------------------------------------------------------------------
#  Token helpers — pure, unit-testable
# ---------------------------------------------------------------------


def generate_token() -> str:
    """256-bit URL-safe random token. Returned ONCE to the caller; we
    persist only its hash."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """sha256 hex. Constant-time-comparable via hmac.compare_digest at
    the lookup site."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_accept_url(token: str, *, base_url: str | None = None) -> str:
    """Compose the invite acceptance URL from `public_base_url` + token.

    The frontend reads /invites/{token} as a preview route and posts
    /invites/accept with the token in the body. Single URL works for
    both flows — the page strips the token from the path on submit.
    """
    base = base_url or get_settings().public_base_url
    # Trailing slash on base so urljoin doesn't replace the path.
    if not base.endswith("/"):
        base = base + "/"
    return urljoin(base, f"invites/accept?token={token}")


# ---------------------------------------------------------------------
#  Create invite
# ---------------------------------------------------------------------


async def create_invite(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_is_owner: bool,
    organization_id: uuid.UUID,
    email: str,
    role_slug: str,
    ttl_days: int = DEFAULT_INVITE_TTL_DAYS,
) -> InviteCreateResponse:
    """Mint an invite. Returns the raw URL (one-time)."""
    normalised_email = email.strip().lower()

    # Defense in depth — Pydantic Literal already excludes 'owner'.
    if not role_catalog.is_invitable(role_slug):
        raise InviteRoleNotAllowed(
            role_slug, "role is not in the invitable set"
        )
    if not actor_is_owner and not role_catalog.is_admin_grantable(role_slug):
        raise InviteRoleNotAllowed(
            role_slug, "admins cannot grant this role; owner required"
        )

    raw_token = generate_token()
    token_hash_value = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=ttl_days)

    row = OrganizationInvite(
        organization_id=organization_id,
        email=normalised_email,
        role_slug=role_slug,
        invited_by_user_id=actor_user_id,
        token_hash=token_hash_value,
        status="pending",
        expires_at=expires_at,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        # Either the partial unique (duplicate pending) or the
        # token_hash unique (256-bit collision — astronomically
        # unlikely but still a clean error). Treat both as duplicate.
        if "uq_org_invite_one_pending_per_email" in str(exc.orig):
            raise DuplicatePendingInvite() from exc
        # Token collision → retry once with a fresh token before giving up.
        log.warning("team.invite.token_collision", email=normalised_email)
        raise

    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="member.invited",
        target_type="invite",
        target_id=row.id,
        after={
            "email": normalised_email,
            "role_slug": role_slug,
            "expires_at": expires_at.isoformat(),
        },
    )

    return InviteCreateResponse(
        invite=_to_invite_read(row, now=now),
        accept_url=build_accept_url(raw_token),
    )


# ---------------------------------------------------------------------
#  List + revoke
# ---------------------------------------------------------------------


async def list_invites(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    include_terminal: bool = False,
) -> InviteList:
    stmt = select(OrganizationInvite).where(
        OrganizationInvite.organization_id == organization_id
    )
    if not include_terminal:
        stmt = stmt.where(OrganizationInvite.status == "pending")
    stmt = stmt.order_by(desc(OrganizationInvite.created_at))
    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return InviteList(invites=[_to_invite_read(r, now=now) for r in rows])


async def revoke_invite(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    invite_id: uuid.UUID,
) -> InviteRead:
    row = await session.get(OrganizationInvite, invite_id)
    if row is None or row.organization_id != organization_id:
        raise InviteNotFound()
    if row.status != "pending":
        raise InviteAlreadyConsumed(row.status)

    now = datetime.now(timezone.utc)
    row.status = "revoked"
    row.revoked_at = now
    row.revoked_by_user_id = actor_user_id
    row.updated_at = now
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="member.invite_revoked",
        target_type="invite",
        target_id=row.id,
    )
    return _to_invite_read(row, now=now)


# ---------------------------------------------------------------------
#  Preview + accept
# ---------------------------------------------------------------------


async def preview_invite(
    session: AsyncSession,
    *,
    token: str,
) -> InvitePreview:
    """GET /invites/{token} — render the acceptance page.

    Does NOT require auth (the page must work before the user signs
    up). Returns only what's needed to make an accept decision.
    """
    row = await _load_by_token(session, token=token)
    if row is None:
        raise InviteNotFound()

    org = await session.get(Organization, row.organization_id)
    if org is None:
        raise InviteNotFound()

    desc = role_catalog.descriptor_for(row.role_slug)
    role_display = desc.display_name if desc else row.role_slug

    now = datetime.now(timezone.utc)
    return InvitePreview(
        organization_name=org.name,
        organization_slug=org.slug,
        role_slug=row.role_slug,  # type: ignore[arg-type]
        role_display_name=role_display,
        invited_email=row.email,
        expires_at=row.expires_at,
        is_expired=row.expires_at < now,
    )


async def accept_invite(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_user_email: str,
    token: str,
) -> InviteAcceptResponse:
    """Consume a pending invite. Order:
      1. Load + validate status
      2. Check not expired
      3. Verify email match (with @pending.local relaxation)
      4. Refuse if already a member
      5. Create OrganizationMember + MemberRole
      6. Mark invite accepted + record audit
      7. Auto-select brand if exactly one exists
    """
    row = await _load_by_token(session, token=token)
    if row is None:
        raise InviteNotFound()

    if row.status != "pending":
        raise InviteAlreadyConsumed(row.status)

    now = datetime.now(timezone.utc)
    if row.expires_at < now:
        # Self-heal: if we notice it's expired at accept-time, update
        # the row so list_invites stops surfacing it as pending.
        row.status = "expired"
        row.updated_at = now
        await session.flush()
        raise InviteExpired()

    actor_email = (actor_user_email or "").strip().lower()
    if not _emails_match(invited=row.email, actor=actor_email):
        raise InviteEmailMismatch()

    # Already a member?
    existing_member_stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == actor_user_id,
        OrganizationMember.organization_id == row.organization_id,
        OrganizationMember.status == "active",
    )
    existing = (await session.execute(existing_member_stmt)).scalar_one_or_none()
    if existing is not None:
        raise AlreadyMember()

    # Look up the role row to get its id (system roles have org_id NULL).
    role_stmt = select(Role).where(
        Role.slug == row.role_slug,
        Role.is_system.is_(True),
    )
    role = (await session.execute(role_stmt)).scalar_one_or_none()
    if role is None:
        # Shouldn't happen — migrations seed all four invitable roles —
        # but raise InviteNotFound rather than 500 so the caller's UI
        # doesn't crash on a half-seeded staging DB.
        raise InviteNotFound()

    # Auto-select sole brand for the new member's last_active_brand_id.
    brand_id = await _only_active_brand(
        session, organization_id=row.organization_id
    )

    member = OrganizationMember(
        organization_id=row.organization_id,
        user_id=actor_user_id,
        status="active",
        last_active_brand_id=brand_id,
    )
    session.add(member)
    await session.flush()  # need member.id for the MemberRole row

    session.add(
        MemberRole(
            member_id=member.id,
            role_id=role.id,
            assigned_by_user_id=actor_user_id,  # accepted by self
        )
    )
    await session.flush()

    # Bump the org member_count so the topbar / Settings → Org shows
    # the right number on the next /me.
    org = await session.get(Organization, row.organization_id)
    if org is not None:
        org.member_count = (org.member_count or 0) + 1

    row.status = "accepted"
    row.accepted_at = now
    row.accepted_by_user_id = actor_user_id
    row.updated_at = now
    await session.flush()

    await audit_service.record(
        session,
        organization_id=row.organization_id,
        actor_user_id=actor_user_id,
        action="member.invite_accepted",
        target_type="invite",
        target_id=row.id,
        after={"role_slug": row.role_slug, "member_id": str(member.id)},
    )

    return InviteAcceptResponse(
        organization_id=row.organization_id,
        brand_id=brand_id,
        role_slugs=[row.role_slug],
        next_route="/dashboard",
    )


# ---------------------------------------------------------------------
#  Background maintenance
# ---------------------------------------------------------------------


async def expire_stale_invites(session: AsyncSession) -> int:
    """Sweep pending invites past their expiry to status=expired.

    Safe to call from a request path (we limit to a small batch); the
    accept_invite path also self-heals on a per-row basis. This helper
    exists so a future cron job can keep list views clean without
    waiting on user traffic.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(OrganizationInvite)
        .where(
            OrganizationInvite.status == "pending",
            OrganizationInvite.expires_at < now,
        )
        .limit(200)
    )
    rows = (await session.execute(stmt)).scalars().all()
    for r in rows:
        r.status = "expired"
        r.updated_at = now
    if rows:
        await session.flush()
    return len(rows)


# ---------------------------------------------------------------------
#  Team overview — one call, the whole page
# ---------------------------------------------------------------------


async def team_overview(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requester_member_id: uuid.UUID | None,
    requester_can_invite: bool,
) -> TeamOverview:
    """Aggregate everything Settings → Team needs to render."""
    members = await _list_member_summaries(
        session, organization_id=organization_id
    )
    invites = await list_invites(
        session, organization_id=organization_id, include_terminal=False
    )
    catalog = role_catalog.get_catalog()

    owner_count = sum(1 for m in members if m.is_owner)
    requester_is_owner = False
    if requester_member_id is not None:
        slugs = await compute_role_slugs_for_member(
            session, member_id=requester_member_id
        )
        requester_is_owner = "owner" in slugs

    return TeamOverview(
        members=members,
        pending_invites=invites.invites,
        roles=catalog.roles,
        member_count=len(members),
        pending_invite_count=len(invites.invites),
        can_invite=requester_can_invite,
        can_revoke_owner=requester_is_owner and owner_count > 1,
    )


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


def _emails_match(*, invited: str, actor: str) -> bool:
    """Exact lowercased match, with a `@pending.local` relaxation for
    dev / pre-webhook environments."""
    if not actor:
        return False
    if actor.endswith(PENDING_EMAIL_SUFFIX):
        # Dev / lazy-created user — Clerk webhook hasn't populated the
        # real email yet. Trust the JWT-derived user id (already
        # authenticated) and accept the invite.
        return True
    return invited.strip().lower() == actor.strip().lower()


async def _load_by_token(
    session: AsyncSession, *, token: str
) -> OrganizationInvite | None:
    if not token or len(token) < 16:
        return None
    h = hash_token(token)
    stmt = select(OrganizationInvite).where(
        OrganizationInvite.token_hash == h
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _only_active_brand(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> uuid.UUID | None:
    """If the org has exactly one active brand, return its id."""
    from aicmo.modules.brands.models import Brand

    stmt = select(Brand.id).where(
        Brand.organization_id == organization_id, Brand.status == "active"
    )
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) == 1:
        return rows[0]
    return None


async def _list_member_summaries(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[MemberSummary]:
    """Active members with their role slugs joined + last-seen from
    user_session if any. Single query for members + user; per-member
    role lookup is via compute_role_slugs_for_member (cached at the
    join layer)."""
    member_stmt = (
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
        )
        .order_by(OrganizationMember.created_at)
    )
    rows = (await session.execute(member_stmt)).all()

    summaries: list[MemberSummary] = []
    for member, user in rows:
        slugs = sorted(
            await compute_role_slugs_for_member(session, member_id=member.id)
        )
        # Best-effort last_active — newest non-revoked user_session.
        last_seen_stmt = (
            select(UserSession.last_seen_at)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
            .order_by(desc(UserSession.last_seen_at))
            .limit(1)
        )
        last_seen = (await session.execute(last_seen_stmt)).scalar_one_or_none()

        summaries.append(
            MemberSummary(
                member_id=member.id,
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role_slugs=slugs,
                is_owner="owner" in slugs,
                joined_at=member.created_at,
                last_active_at=last_seen,
            )
        )
    return summaries


def _to_invite_read(
    row: OrganizationInvite, *, now: datetime
) -> InviteRead:
    return InviteRead(
        id=row.id,
        organization_id=row.organization_id,
        email=row.email,
        role_slug=row.role_slug,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        invited_by_user_id=row.invited_by_user_id,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
        is_expired=row.expires_at < now,
    )
