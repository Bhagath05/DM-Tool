"""HTTP surface for the LinkedIn poster studio (flag-gated by `poster_enabled`).

  POST /poster/linkedin/compose  topic → branded poster + caption
  POST /poster/linkedin/render   edited fields → re-rendered poster (no LLM)
  GET  /poster/capabilities      is a renderer available on this host?
  GET  /poster/media             signed PNG serving (public, expiring)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.poster import media, service
from aicmo.modules.poster.render import PosterRenderUnavailable, renderer_available
from aicmo.modules.poster.schemas import (
    LinkedInComposeRequest,
    LinkedInComposeResult,
    LinkedInRenderRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/poster", tags=["poster"])


def _guard() -> None:
    if not getattr(get_settings(), "poster_enabled", False):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "LinkedIn poster studio is disabled."
        )


@router.get("/capabilities")
async def capabilities(
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> dict[str, bool]:
    return {
        "enabled": bool(getattr(get_settings(), "poster_enabled", False)),
        "renderer_available": renderer_available(),
    }


@router.post("/linkedin/compose", response_model=LinkedInComposeResult)
async def compose(
    payload: LinkedInComposeRequest,
    tenant: TenantContext = Depends(require_permission("content.create")),
    session: AsyncSession = Depends(get_db),
) -> LinkedInComposeResult:
    _guard()
    try:
        return await service.compose_linkedin(
            session,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            req=payload,
        )
    except PosterRenderUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Image renderer unavailable: {exc}"
        ) from exc


@router.post("/linkedin/render", response_model=LinkedInComposeResult)
async def render(
    payload: LinkedInRenderRequest,
    tenant: TenantContext = Depends(require_permission("content.create")),
    session: AsyncSession = Depends(get_db),
) -> LinkedInComposeResult:
    _guard()
    try:
        return await service.rerender_linkedin(
            session,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            fields=payload.fields,
            generate_image=payload.generate_image,
        )
    except PosterRenderUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Image renderer unavailable: {exc}"
        ) from exc


@router.get("/media")
async def media_get(
    k: str = Query(...), exp: int = Query(...), sig: str = Query(...)
) -> Response:
    """Serve a rendered poster by signed token. Public (no auth header) so
    <img src> and the publish step can fetch it; the HMAC + expiry gate it."""
    key = media.verify(k, exp, sig)
    if not key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired link.")
    from aicmo.modules.creative.storage.base import StorageRef
    from aicmo.modules.creative.storage.registry import get_storage_backend

    backend = get_storage_backend()
    try:
        data = backend.read(StorageRef(backend=get_settings().media_backend, key=key))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Poster not found.") from exc
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=600"},
    )
