"""The single authoritative authentication dependency.

`require_user` is the one place a request is authenticated: read the HttpOnly
session cookie, resolve it to an active session + active user, and hand back an
`AuthContext`. It is deliberately the *only* auth entry point — routes and the
tenant resolver depend on it rather than re-reading cookies. Authentication
stops here; authorization (tenant/RBAC/RLS) continues in
`tenancy/dependencies.py`, which consumes this context unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import sessions
from aicmo.auth.cookies import set_session_cookie
from aicmo.auth.csrf import is_csrf_valid, is_origin_allowed
from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.users.models import User

log = structlog.get_logger()


@dataclass(frozen=True)
class AuthContext:
    """Identity of the authenticated caller. `user_id` is the DM user uuid as a
    string (kept as the field name so downstream code is untouched); `user_uuid`
    is the same value typed. `org_id`/`claims` are retained for signature
    compatibility with call sites and are inert under first-party auth."""

    user_id: str
    user_uuid: uuid.UUID
    session_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    org_id: str | None = None
    claims: dict = field(default_factory=dict)


async def require_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AuthContext:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    user_session = await sessions.resolve_session(session, raw_token=raw or "")
    if user_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await session.get(User, user_session.user_id)
    if user is None or user.status != "active":
        # Session is orphaned or the account is suspended/deleted → reject.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Idle rotation: if the token has outlived the rotation window, swap it and
    # re-set the cookie on the shared response. Fresh-token-on-login already
    # defeats fixation; this shrinks the window for a silently-stolen token.
    rotated = await sessions.rotate_if_stale(session, user_session=user_session, settings=settings)
    if rotated:
        set_session_cookie(response, settings=settings, token=rotated)
        # Persist the new token hash immediately: we've already handed the new
        # token to the client via the cookie, so if this request's transaction
        # later rolls back (most GET handlers never commit) the client would be
        # left holding a token the DB doesn't know — an accidental logout.
        await session.commit()

    return AuthContext(
        user_id=str(user.id),
        user_uuid=user.id,
        session_id=str(user_session.id),
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
    )


async def optional_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AuthContext | None:
    """Like `require_user` but returns None instead of 401 when unauthenticated.
    For endpoints that render differently for anonymous vs signed-in callers."""
    try:
        return await require_user(request, response, session)
    except HTTPException:
        return None


def require_csrf(request: Request) -> None:
    """Reject a state-changing request that fails the double-submit CSRF check.
    Attach to mutating auth routes via `dependencies=[Depends(require_csrf)]`."""
    if not is_csrf_valid(request, get_settings()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def require_same_origin(request: Request) -> None:
    """Origin allowlist guard for cookieless auth POSTs (signup/signin/reset),
    which have no CSRF cookie yet. Blocks cross-site submission such as login
    CSRF without requiring a pre-existing token."""
    if not is_origin_allowed(request, get_settings()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cross-origin request rejected")


CurrentUser = Depends(require_user)
