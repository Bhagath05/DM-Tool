"""Phase 10.2c — HTTP surface for security.

Two routers:

  `router`        — authenticated; gated on require_tenant
                    (self-service settings, no extra permission slug)
  `public_router` — unauthenticated; the Clerk webhook receiver,
                    verified by Svix signature instead of bearer token

Exception → status mapping:

  SessionNotFound                  → 404
  CurrentSessionRevokeRefused      → 409
  EventTypeNotAllowedFromClient    → 403
  WebhookVerificationError         → 400 (with generic detail — never
                                          leak which check failed)
  webhook disabled (no secret)     → 503

All client errors emit a structlog warning so a noisy attacker shows
up in dashboards without us paying full Sentry quota per event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth import clerk_webhook
from aicmo.auth.clerk import AuthContext, require_user
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
    current_clerk = _current_session_id(auth, request)
    return await service.list_sessions(
        session,
        user_id=tenant.user_uuid,
        current_clerk_session_id=current_clerk,
        include_revoked=include_revoked,
    )


@router.post(
    "/sessions/{session_id}/revoke",
    response_model=RevokeSessionResponse,
    summary="Revoke one session (calls Clerk admin API)",
)
async def revoke_session_endpoint(
    session_id: uuid.UUID,
    request: Request,
    tenant: TenantContext = Depends(_RequireTenant),
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> RevokeSessionResponse:
    current_clerk = _current_session_id(auth, request)
    try:
        return await service.mark_session_revoked(
            session,
            user_id=tenant.user_uuid,
            session_row_id=session_id,
            current_clerk_session_id=current_clerk,
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
            detail=(
                "Cannot revoke your current session from this endpoint — "
                "sign out instead."
            ),
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
    current_clerk = _current_session_id(auth, request)
    return await service.revoke_all_sessions(
        session,
        user_id=tenant.user_uuid,
        current_clerk_session_id=current_clerk,
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
                "the client — must arrive via the Clerk webhook."
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


# ---------------------------------------------------------------------
#  Public — Clerk webhook receiver
# ---------------------------------------------------------------------


@public_router.post(
    "/clerk",
    status_code=status.HTTP_200_OK,
    summary="Receive a Clerk webhook delivery (Svix-signed)",
    include_in_schema=False,  # webhooks aren't part of the public OpenAPI
)
async def clerk_webhook_receiver(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Verify signature → parse JSON → dispatch.

    503 when no signing secret configured (intentional fail-closed; we
    never accept unverified payloads even in dev).
    400 when signature / timestamp / format checks fail (generic detail
    so we don't leak which check tripped).
    200 with `{handled: bool, ...}` for any verified delivery — even
    if the event type is unrecognised, so Clerk doesn't retry forever.
    """
    body = await request.body()
    try:
        verified = clerk_webhook.verify(
            headers=dict(request.headers),
            body=body,
        )
    except clerk_webhook.WebhookVerificationError as exc:
        if exc.reason == "webhook_disabled":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook receiver disabled — CLERK_WEBHOOK_SIGNING_SECRET not set.",
            )
        log.warning(
            "security.webhook.reject",
            reason=exc.reason,
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook verification failed.",
        )

    import json

    try:
        payload = json.loads(verified.body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body.",
        )

    return await service.dispatch_webhook(
        session,
        payload=payload,
        ip_address=_client_ip(request),
    )


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _current_session_id(auth: AuthContext, request: Request) -> str | None:
    """Prefer the session id from the verified JWT claims (AuthContext).
    Fall back to an explicit `X-Clerk-Session-Id` header — used in dev /
    demo mode where the JWT path isn't exercised."""
    if auth.session_id:
        return auth.session_id
    return request.headers.get("x-clerk-session-id")


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP. Prefer the first X-Forwarded-For entry
    when behind a proxy, fall back to socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
