"""Phase 10.2d — Team management HTTP surface.

Two routers:

  `router`        — authenticated; tenant-scoped; gated on `team.manage`
                    (matches existing orgs/router member endpoints)

  `public_router` — authenticated (require_user) but NO tenant headers.
                    The invitee may not yet be a member of the inviting
                    org, so `require_tenant` would reject them with 400
                    "missing tenant headers". Invite acceptance has its
                    own auth path: bearer token only, no X-Organization-Id.

Mount in main.py:
  app.include_router(team_router, prefix="/api/v1")
  app.include_router(team_public_router, prefix="/api/v1")

Endpoints:

  Authenticated (team.manage required unless noted):
    GET    /team                          — overview
    GET    /team/roles                    — catalog (NO permission; static)
    POST   /team/invites
    GET    /team/invites
    POST   /team/invites/{invite_id}/revoke

  Authenticated-without-tenant (invite acceptance):
    GET    /invites/{token}               — preview (no auth required —
                                            the invitee may not have an
                                            account yet)
    POST   /invites/accept                — consume (require_user only)
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.db.session import get_db
from aicmo.modules.team import role_catalog, service
from aicmo.modules.team.schemas import (
    InviteAcceptRequest,
    InviteAcceptResponse,
    InviteCreate,
    InviteCreateResponse,
    InviteList,
    InvitePreview,
    InviteRead,
    RoleCatalog,
    TeamOverview,
)
from aicmo.modules.users.models import User
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant

log = structlog.get_logger()


router = APIRouter(prefix="/team", tags=["team"])
public_router = APIRouter(prefix="/invites", tags=["invites"])

# `team.manage` is the existing permission slug from the W1-14 seed —
# owners + admins hold it. brand_optional=True because team membership
# is org-scoped, not brand-scoped.
_RequireTeamManage = require_permission("team.manage", brand_optional=True)
_RequireTenant = require_tenant(brand_optional=True)


# ---------------------------------------------------------------------
#  Authenticated — overview + catalog
# ---------------------------------------------------------------------


@router.get(
    "",
    response_model=TeamOverview,
    summary="Aggregated team page payload — members + invites + roles",
)
async def get_overview(
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> TeamOverview:
    """Anyone in the org can see the team page (read-only); only members
    with `team.manage` see the actions. We pass `can_invite` to the
    response so the UI knows which affordances to render — no need for
    a separate /me-style call."""
    return await service.team_overview(
        session,
        organization_id=tenant.organization_id,
        requester_member_id=tenant.member_id,
        requester_can_invite="team.manage" in tenant.permissions,
    )


@router.get(
    "/roles",
    response_model=RoleCatalog,
    summary="Canonical 4-role catalog (static)",
)
async def get_role_catalog(
    _tenant: TenantContext = Depends(_RequireTenant),
) -> RoleCatalog:
    """Same response for every user. Tenant-gated only because the
    settings page is behind auth; the data itself is non-sensitive."""
    return role_catalog.get_catalog()


# ---------------------------------------------------------------------
#  Authenticated — invites (team.manage required)
# ---------------------------------------------------------------------


@router.post(
    "/invites",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invite. Returns the accept URL ONCE.",
)
async def post_invite(
    payload: InviteCreate,
    tenant: TenantContext = Depends(_RequireTeamManage),
    session: AsyncSession = Depends(get_db),
) -> InviteCreateResponse:
    actor_is_owner = "owner" in tenant.role_slugs
    try:
        return await service.create_invite(
            session,
            actor_user_id=tenant.user_uuid,
            actor_is_owner=actor_is_owner,
            organization_id=tenant.organization_id,
            email=payload.email,
            role_slug=payload.role_slug,
        )
    except service.InviteRoleNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot invite as {exc.role_slug}: {exc.reason}",
        )
    except service.DuplicatePendingInvite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A pending invite for this email already exists. Revoke "
                "the previous invite first or wait for it to expire."
            ),
        )


@router.get(
    "/invites",
    response_model=InviteList,
    summary="List org invites (pending by default)",
)
async def get_invites(
    include_terminal: bool = Query(
        default=False,
        description="Include accepted / revoked / expired invites in history view.",
    ),
    tenant: TenantContext = Depends(_RequireTeamManage),
    session: AsyncSession = Depends(get_db),
) -> InviteList:
    return await service.list_invites(
        session,
        organization_id=tenant.organization_id,
        include_terminal=include_terminal,
    )


@router.post(
    "/invites/{invite_id}/revoke",
    response_model=InviteRead,
    summary="Revoke a pending invite",
)
async def revoke_invite_endpoint(
    invite_id: uuid.UUID = Path(...),
    tenant: TenantContext = Depends(_RequireTeamManage),
    session: AsyncSession = Depends(get_db),
) -> InviteRead:
    try:
        return await service.revoke_invite(
            session,
            actor_user_id=tenant.user_uuid,
            organization_id=tenant.organization_id,
            invite_id=invite_id,
        )
    except service.InviteNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found"
        )
    except service.InviteAlreadyConsumed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot revoke invite — already {exc.current_status}.",
        )


# ---------------------------------------------------------------------
#  Acceptance flow — auth required, but NO tenant headers
# ---------------------------------------------------------------------


@public_router.get(
    "/{token}",
    response_model=InvitePreview,
    summary="Preview an invite — what org + role would be granted",
)
async def preview_invite_endpoint(
    token: str = Path(..., min_length=16, max_length=128),
    session: AsyncSession = Depends(get_db),
) -> InvitePreview:
    """Public — no auth. The invite URL is the credential; we don't
    want to force the invitee to sign in just to see what they were
    invited to (and if they don't have an account yet, they need this
    info before signing up)."""
    try:
        return await service.preview_invite(session, token=token)
    except service.InviteNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found"
        )


@public_router.post(
    "/accept",
    response_model=InviteAcceptResponse,
    summary="Accept an invite — creates membership + role assignment",
)
async def accept_invite_endpoint(
    payload: InviteAcceptRequest,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> InviteAcceptResponse:
    """Requires bearer token (a user must be signed in to be added to
    an org), but does NOT require X-Organization-Id — the invitee
    isn't a member of any org yet (the invite IS the membership)."""
    # Load the User row by clerk_user_id. Mirror of the lazy-create
    # in `require_tenant`, simplified — accept-invite is the only path
    # that needs an authenticated user but no tenant scope.
    user_stmt = select(User).where(User.clerk_user_id == auth.user_id)
    user = (await session.execute(user_stmt)).scalar_one_or_none()
    if user is None:
        # Lazy-create — same shape as tenancy.dependencies._get_or_create_user
        user = User(
            clerk_user_id=auth.user_id,
            email=f"{auth.user_id}@pending.local",
            status="active",
        )
        session.add(user)
        await session.flush()

    try:
        return await service.accept_invite(
            session,
            actor_user_id=user.id,
            actor_user_email=user.email,
            token=payload.token,
        )
    except service.InviteNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found"
        )
    except service.InviteExpired:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite has expired. Ask for a new one.",
        )
    except service.InviteAlreadyConsumed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This invite was already {exc.current_status}.",
        )
    except service.InviteEmailMismatch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This invite was sent to a different email address. "
                "Sign in with the invited email or ask for a new invite."
            ),
        )
    except service.AlreadyMember:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this workspace.",
        )
