"""Media-serving endpoint.

GET /media/{rendered_id}?exp=<unix>&sig=<hex>

Unauthenticated by design — anyone with a valid signed URL can fetch.
That's the whole point of signed URLs. Signature verification + expiry
check keeps it bounded. The signing key is `media_signing_secret` (or
`clerk_secret_key` as a fallback).

We serve as `image/png` by default since OpenAI returns PNG; the
RenderedVisual row's mime_type is the source of truth in case providers
diverge.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from aicmo.db.session import SessionLocal
from aicmo.modules.visuals.media_url import verify_signed_url
from aicmo.modules.visuals.render import resolve_file_path
from aicmo.modules.visuals.render_models import RenderedVisual

# Mounted at /api/v1 alongside other public routers. The signed URL itself
# is the authentication mechanism — no Clerk dependency.
public_router = APIRouter(prefix="/media", tags=["media"])


@public_router.get("/{rendered_id}")
async def serve_render(
    rendered_id: uuid.UUID,
    exp: int = Query(...),
    sig: str = Query(...),
):
    ok, reason = verify_signed_url(rendered_id, exp, sig)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid or expired media link ({reason}).",
        )

    # Look up the row to get the canonical file path + mime type. Storing
    # the path on the row (rather than computing it from id) means we can
    # move MEDIA_DIR between runs without breaking older URLs.
    async with SessionLocal() as session:
        stmt = select(RenderedVisual).where(RenderedVisual.id == rendered_id)
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found.",
        )

    file_path = row.file_path or resolve_file_path(rendered_id)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file is missing on disk.",
        )

    return FileResponse(
        file_path,
        media_type=row.mime_type or "image/png",
        # 7-day browser cache: the signed URL is the cache key, so reusing
        # is safe; the URL itself expires after 30 days regardless.
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )
