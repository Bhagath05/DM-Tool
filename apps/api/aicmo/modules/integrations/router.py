"""Integration framework — HTTP surface.

Seven endpoints, every one a thin wrapper over `service.*`. Exception
mapping happens here so the service layer is HTTP-agnostic.

Permission contract:
  - Catalog reads (GET):  `analytics.view`  — same as existing read paths.
  - Mutations (POST/DELETE for connect/sync/disconnect): `analytics.view`
    today. When real OAuth ships (Phase 11), this tightens to an
    admin-tier permission (`integrations.manage` or similar).
  - OAuth callback: UNAUTHENTICATED public endpoint. The state token
    is the only credential — it carries the connection id and is
    signed with the integration encryption key, so a spoofed call
    can't redirect tokens to someone else's connection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.integrations import oauth_state, service
from aicmo.modules.integrations.registry import UnknownProvider
from aicmo.modules.integrations.schemas import (
    CatalogEntry,
    CatalogResponse,
    ConnectionRead,
    ConnectResponse,
    HealthResponse,
    SyncResponse,
)
from aicmo.modules.integrations.state import InvalidStateTransition
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

# Public (no tenant) router for the OAuth callback. Mounted alongside
# the authenticated router but on a separate APIRouter so we don't
# accidentally gate it behind `require_permission`.
router = APIRouter(prefix="/integrations", tags=["integrations"])
public_router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------
#  Catalog
# ---------------------------------------------------------------------


@router.get("", response_model=CatalogResponse)
async def list_catalog(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> CatalogResponse:
    """Every registered provider, paired with this tenant's current
    connection state (if any). Foundation for the Settings ·
    Integrations grid."""
    items = await service.build_catalog(session, tenant=tenant)
    return CatalogResponse(items=items)


@router.get("/{slug}", response_model=CatalogEntry)
async def get_provider(
    slug: str,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> CatalogEntry:
    try:
        return await service.get_provider_detail(
            session, tenant=tenant, slug=slug
        )
    except UnknownProvider as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )


# ---------------------------------------------------------------------
#  Connect → OAuth → Disconnect
# ---------------------------------------------------------------------


@router.post(
    "/{slug}/connect",
    response_model=ConnectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_connect(
    slug: str,
    redirect_uri: str = Query(
        ...,
        description=(
            "OAuth callback URL — must be one of the URLs registered "
            "with the provider's developer console. Typically points "
            "at /api/v1/integrations/oauth/callback on this API."
        ),
    ),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> ConnectResponse:
    try:
        conn, authorize_url = await service.start_connect(
            session, tenant=tenant, slug=slug, redirect_uri=redirect_uri
        )
    except UnknownProvider as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    except service.AlreadyConnected as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    except service.ProviderNotReady as exc:
        # Honest 501 — the framework works; this provider just isn't
        # implemented yet. Phase 10.2a ships ALL providers as stubs,
        # so every call to this endpoint hits this branch.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        )
    except InvalidStateTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return ConnectResponse(
        connection_id=conn.id,
        authorize_url=authorize_url,
        state=conn.state,  # type: ignore[arg-type]
    )


@public_router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(..., description="OAuth code from the provider."),
    state: str = Query(..., description="Signed state we issued at connect()."),
    redirect_uri: str = Query(
        ..., description="Must match the redirect_uri sent to start_connect."
    ),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Provider redirected back — exchange code, then redirect to settings."""
    from aicmo.config import get_settings

    settings = get_settings()
    app_base = settings.public_base_url or "http://localhost:3000"
    success_url = f"{app_base}/settings/integrations?connected=1"
    error_url = f"{app_base}/settings/integrations?error=oauth_failed"

    try:
        conn = await service.handle_callback(
            session, state_token=state, code=code, redirect_uri=redirect_uri
        )
    except oauth_state.InvalidOAuthState:
        return RedirectResponse(url=error_url)
    except service.UnknownConnection:
        return RedirectResponse(url=error_url)
    except service.ProviderNotReady:
        return RedirectResponse(url=error_url)
    except Exception:  # noqa: BLE001
        return RedirectResponse(url=error_url)

    slug = conn.provider_slug
    return RedirectResponse(url=f"{success_url}&provider={slug}")


@router.post(
    "/{connection_id}/disconnect",
    response_model=ConnectionRead,
)
async def disconnect(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> ConnectionRead:
    try:
        conn = await service.disconnect(
            session, tenant=tenant, connection_id=connection_id
        )
    except service.UnknownConnection as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    except InvalidStateTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return ConnectionRead.model_validate(conn)


# ---------------------------------------------------------------------
#  Sync + health
# ---------------------------------------------------------------------


@router.post(
    "/{connection_id}/sync",
    response_model=SyncResponse,
)
async def trigger_sync(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> SyncResponse:
    try:
        result = await service.sync(
            session, tenant=tenant, connection_id=connection_id
        )
    except service.UnknownConnection as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    except service.NotConnectable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    except service.ProviderNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        )

    # Re-fetch the connection to surface the latest state to the caller.
    conn = await service._load_owned_connection(  # noqa: SLF001
        session, tenant=tenant, connection_id=connection_id
    )
    return SyncResponse(
        connection_id=conn.id,
        state=conn.state,  # type: ignore[arg-type]
        started_at=result.started_at,
        finished_at=result.finished_at,
        rows_pulled=result.rows_pulled,
        error_message=result.error_message,
    )


@router.get(
    "/{connection_id}/health",
    response_model=HealthResponse,
)
async def health(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> HealthResponse:
    try:
        conn = await service._load_owned_connection(  # noqa: SLF001
            session, tenant=tenant, connection_id=connection_id
        )
    except service.UnknownConnection as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    return HealthResponse(
        connection_id=conn.id,
        provider_slug=conn.provider_slug,
        state=conn.state,  # type: ignore[arg-type]
        last_sync_at=conn.last_sync_at,
        last_error_at=conn.last_error_at,
        error_message=conn.error_message,
    )
