"""First-party authentication API.

All routes live under /api/v1/auth. Guards:
  * cookieless POSTs (signup/signin/verify/reset) → require_same_origin
    (blocks cross-site submission such as login CSRF; no CSRF cookie exists yet)
  * authenticated mutations (signout/change-password/revoke-all/disable) →
    require_user + require_csrf (double-submit)
Every mutating handler commits its own unit of work — get_db does not commit.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import service
from aicmo.auth.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from aicmo.auth.csrf import generate_csrf_token
from aicmo.auth.dependencies import (
    AuthContext,
    require_csrf,
    require_same_origin,
    require_user,
)
from aicmo.auth.models import UserSession
from aicmo.auth.schemas import (
    ChangePasswordRequest,
    GenericMessage,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    SessionUser,
    SigninRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from aicmo.auth.service import WeakPassword
from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.users.models import User

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Enumeration-safe generic responses. Signup/reset never confirm existence.
_SIGNUP_OK = GenericMessage(
    message="If that email can be registered, a verification link has been sent."
)
_RESET_OK = GenericMessage(
    message="If an account exists for that email, a reset link has been sent."
)


def _client_ip(request: Request) -> str | None:
    # Trust the app's proxy configuration is handled upstream; fall back to the
    # socket peer. Only used for throttling + audit, never for authorization.
    return request.client.host if request.client else None


@router.post("/signup", response_model=GenericMessage, dependencies=[Depends(require_same_origin)])
async def signup(
    payload: SignupRequest,
    session: AsyncSession = Depends(get_db),
) -> GenericMessage:
    try:
        await service.signup(
            session,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            settings=get_settings(),
        )
    except WeakPassword as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await session.commit()
    return _SIGNUP_OK


@router.post("/signin", response_model=SessionUser, dependencies=[Depends(require_same_origin)])
async def signin(
    payload: SigninRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> SessionUser:
    settings = get_settings()
    result = await service.signin(
        session,
        email=payload.email,
        password=payload.password,
        settings=settings,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    if result.locked:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )
    if not result.ok or result.user is None or result.session_token is None:
        # One generic message for unknown-email AND wrong-password AND
        # unverified — never reveal which.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    set_session_cookie(response, settings=settings, token=result.session_token)
    set_csrf_cookie(response, settings=settings, token=generate_csrf_token())
    return _session_user(result.user)


@router.post("/signout", response_model=GenericMessage)
async def signout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
) -> GenericMessage:
    settings = get_settings()
    from aicmo.auth import sessions as sessions_store

    raw = request.cookies.get(settings.session_cookie_name)
    us = await sessions_store.resolve_session(session, raw_token=raw or "")
    if us is not None:
        await sessions_store.revoke_session(session, user_session=us)
        await session.commit()
    clear_session_cookie(response, settings=settings)
    clear_csrf_cookie(response, settings=settings)
    return GenericMessage(message="Signed out.")


@router.post(
    "/verify-email", response_model=GenericMessage, dependencies=[Depends(require_same_origin)]
)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db),
) -> GenericMessage:
    ok = await service.verify_email(session, raw_token=payload.token, settings=get_settings())
    await session.commit()
    if not ok:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )
    return GenericMessage(message="Email verified. You can now sign in.")


@router.post(
    "/request-password-reset",
    response_model=GenericMessage,
    dependencies=[Depends(require_same_origin)],
)
async def request_password_reset(
    payload: RequestPasswordResetRequest,
    session: AsyncSession = Depends(get_db),
) -> GenericMessage:
    await service.request_password_reset(session, email=payload.email, settings=get_settings())
    await session.commit()
    return _RESET_OK


@router.post(
    "/reset-password", response_model=GenericMessage, dependencies=[Depends(require_same_origin)]
)
async def reset_password(
    payload: ResetPasswordRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> GenericMessage:
    settings = get_settings()
    try:
        ok = await service.reset_password(
            session,
            raw_token=payload.token,
            new_password=payload.new_password,
            settings=settings,
        )
    except WeakPassword as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await session.commit()
    if not ok:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    # The reset revoked all sessions; clear any cookie this browser still holds.
    clear_session_cookie(response, settings=settings)
    clear_csrf_cookie(response, settings=settings)
    return GenericMessage(message="Password changed. Please sign in.")


@router.post("/change-password", response_model=SessionUser)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
) -> SessionUser:
    settings = get_settings()
    user = await session.get(User, auth.user_uuid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    from aicmo.auth import sessions as sessions_store

    current = await sessions_store.resolve_session(
        session, raw_token=request.cookies.get(settings.session_cookie_name) or ""
    )
    try:
        ok = await service.change_password(
            session,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            settings=settings,
            keep_session_id=current.id if current else None,
        )
    except WeakPassword as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    # Rotate the caller's own session (issue a fresh token) so every previously
    # issued token for this user is now dead, including any copy of the old one.
    if current is not None:
        await sessions_store.revoke_session(session, user_session=current)
    raw, _row = await sessions_store.create_session(
        session,
        user_id=user.id,
        settings=settings,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    set_session_cookie(response, settings=settings, token=raw)
    set_csrf_cookie(response, settings=settings, token=generate_csrf_token())
    return _session_user(user)


@router.post("/revoke-all", response_model=GenericMessage)
async def revoke_all(
    response: Response,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
) -> GenericMessage:
    from aicmo.auth import sessions as sessions_store

    n = await sessions_store.revoke_all_for_user(session, user_id=auth.user_uuid)
    await session.commit()
    clear_session_cookie(response, settings=get_settings())
    clear_csrf_cookie(response, settings=get_settings())
    return GenericMessage(message=f"Signed out of {n} session(s) everywhere.")


@router.post("/disable", response_model=GenericMessage)
async def disable_account(
    response: Response,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
) -> GenericMessage:
    user = await session.get(User, auth.user_uuid)
    if user is not None:
        await service.disable_account(session, user=user)
        await session.commit()
    clear_session_cookie(response, settings=get_settings())
    clear_csrf_cookie(response, settings=get_settings())
    return GenericMessage(message="Account disabled.")


@router.get("/session", response_model=SessionUser)
async def current_session(
    auth: AuthContext = Depends(require_user),
) -> SessionUser:
    """The signed-in identity, or 401 if unauthenticated (the SPA treats 401 as
    'anonymous'). Credentials are never included."""
    return SessionUser(
        id=auth.user_uuid,
        email=auth.email or "",
        display_name=auth.display_name,
        avatar_url=auth.avatar_url,
        email_verified=True,  # require_user only resolves active, usable users
    )


def _session_user(user: User) -> SessionUser:
    return SessionUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        email_verified=user.email_verified_at is not None,
    )


# Re-export so `from aicmo.auth.router import UserSession` stays available if
# ever needed by tests; keeps import graph explicit.
__all__ = ["UserSession", "router"]
