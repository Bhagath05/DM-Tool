"""CRM Email public tracking (Phase 6.5, Slice 4).

Unauthenticated endpoints hit by recipients' email clients — a tracking pixel,
click redirect, and unsubscribe — plus a secret-gated provider webhook for
delivery/bounce/reply events. Mounted under /public/email so the route-guard's
`/api/v1/public/` allowlist covers it (recipients have no session). Each request
is scoped by the unguessable per-email `track_token`, never by a tenant header.
No tracking data is ever fabricated — a row updates only when a real pixel /
click / provider event arrives.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.crm import email_service as svc
from aicmo.modules.crm.email_schemas import ProviderEvent

router = APIRouter(prefix="/public/email", tags=["public"])

# 1x1 transparent GIF — the open-tracking pixel.
_PIXEL = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000"
    "010001000002024401003b"
)


@router.get("/open/{token}")
async def track_open(token: str, session: AsyncSession = Depends(get_db)) -> Response:
    await svc.mark_opened(session, token)
    return Response(content=_PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store"})


@router.get("/click/{token}")
async def track_click(token: str, url: str = Query(...), session: AsyncSession = Depends(get_db)):
    await svc.mark_clicked(session, token)
    # Only ever redirect to an http(s) URL — never javascript:/data: (open-redirect safety).
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid redirect target.")
    return RedirectResponse(url, status_code=302)


@router.get("/unsubscribe/{token}")
async def unsubscribe(token: str, session: AsyncSession = Depends(get_db)) -> Response:
    await svc.mark_unsubscribed(session, token)
    return Response(
        content="<html><body style='font-family:sans-serif'><h3>You're unsubscribed.</h3>"
                "<p>You won't receive further emails from this sequence.</p></body></html>",
        media_type="text/html",
    )


@router.post("/webhook")
async def provider_webhook(
    payload: ProviderEvent,
    x_email_webhook_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest normalised provider events (delivered / bounced / replied). Fail
    closed: disabled (503) until a secret is configured, then constant-time
    compared."""
    secret = get_settings().email_webhook_secret
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Email webhook disabled — no secret configured.")
    if not x_email_webhook_secret or not hmac.compare_digest(x_email_webhook_secret, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret.")
    applied = await svc.apply_provider_event(
        session, event=payload.event, message_id=payload.message_id,
        track_token=payload.track_token, detail=payload.detail,
    )
    return {"applied": applied}
