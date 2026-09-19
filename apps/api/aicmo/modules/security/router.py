"""Phase 10.2c — HTTP surface for security.

Two routers:

  `router`        — authenticated; gated on require_tenant
                    (self-service settings, no extra permission slug)
  `public_router` — reserved (empty) for future signature-verified public
                    webhooks; the legacy Clerk webhook receiver was removed.

Exception → status mapping:

  SessionNotFound                  → 404
  CurrentSessionRevokeRefused      → 409
  EventTypeNotAllowedFromClient    → 403

All client errors emit a structlog warning so a noisy attacker shows
up in dashboards without us paying full Sentry quota per event.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.dependencies import AuthContext, require_user
from aicmo.db.session import get_db
from aicmo.modules.security import service
from aicmo.modules.security.schemas import (
    RevokeAllResponse,
    RevokeSessionResponse,
    SecurityEventCreate,
    SecurityEventList,
    SecurityEventRead,
    SecuritySummary,
    SessionList,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_tenant

log = structlog.get_logger()


router = APIRouter(prefix="/security", tags=["security"])
public_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_RequireTenant = require_tenant(brand_optional=True)


# ---------------------------------------------------------------------
#  Authenticated — sessions
# ---------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=SessionList,
    summary="List the current user's sessions",
)
async def get_sessions(
    request: Request,
    include_revoked: bool = Query(default=False),
    tenant: TenantContext = Depends(_RequireTenant),
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> SessionList:
    current_session = _current_session_id(auth)
    return await service.list_sessions(
        session,
        user_id=tenant.user_uuid,
        current_session_id=current_session,
        include_revoked=include_revoked,
    )


@router.post(
    "/sessions/{session_id}/revoke",
    response_model=RevokeSessionResponse,
    summary="Revoke one session (local store)",
)
async def revoke_session_endpoint(
    session_id: uuid.UUID,
    request: Request,
    tenant: TenantContext = Depends(_RequireTenant),
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> RevokeSessionResponse:
    current_session = _current_session_id(auth)
    try:
        return await service.mark_session_revoked(
            session,
            user_id=tenant.user_uuid,
            session_row_id=session_id,
            current_session_id=current_session,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.SessionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    except service.CurrentSessionRevokeRefused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Cannot revoke your current session from this endpoint — sign out instead."),
        )


@router.post(
    "/sessions/revoke-all",
    response_model=RevokeAllResponse,
    summary="Revoke every session except the current one",
)
async def revoke_all_sessions_endpoint(
    request: Request,
    tenant: TenantContext = Depends(_RequireTenant),
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> RevokeAllResponse:
    current_session = _current_session_id(auth)
    return await service.revoke_all_sessions(
        session,
        user_id=tenant.user_uuid,
        current_session_id=current_session,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


# ---------------------------------------------------------------------
#  Authenticated — events
# ---------------------------------------------------------------------


@router.get(
    "/events",
    response_model=SecurityEventList,
    summary="Paginated security event timeline (newest first)",
)
async def get_events(
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(
        default=None,
        description="Cursor — pass the `occurred_at` of the last event in the previous page.",
    ),
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> SecurityEventList:
    return await service.list_events(
        session,
        user_id=tenant.user_uuid,
        limit=limit,
        before=before,
    )


@router.post(
    "/events",
    response_model=SecurityEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an event the client witnessed (mfa_challenge / failed_login only)",
)
async def post_event(
    payload: SecurityEventCreate,
    request: Request,
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> SecurityEventRead:
    try:
        return await service.record_client_event(
            session,
            user_id=tenant.user_uuid,
            payload=payload,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.EventTypeNotAllowedFromClient as exc:
        log.warning(
            "security.client_event.forbidden",
            event_type=exc.event_type,
            user=str(tenant.user_uuid),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Event type '{exc.event_type}' cannot be recorded from "
                "the client — it is produced server-side only."
            ),
        )


@router.get(
    "/summary",
    response_model=SecuritySummary,
    summary="Top-of-page stats for Settings → Security",
)
async def get_summary(
    tenant: TenantContext = Depends(_RequireTenant),
    session: AsyncSession = Depends(get_db),
) -> SecuritySummary:
    return await service.build_summary(session, user_id=tenant.user_uuid)


# The Clerk webhook receiver (Svix-signed `/webhooks/clerk`) was removed with
# the first-party auth migration — there is no external identity provider to
# receive user/session events from. `public_router` is kept (empty) so its
# mount point stays stable for future signature-verified public webhooks.


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _current_session_id(auth: AuthContext) -> str | None:
    """The caller's first-party session id (`user_sessions.id` as a string),
    resolved by `require_user` from the session cookie. Used to flag the current
    device and to spare it from 'sign out everywhere else'."""
    return auth.session_id


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP. Prefer the first X-Forwarded-For entry
    when behind a proxy, fall back to socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
