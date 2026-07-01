"""Security response headers for the API.

The Next.js frontend already sets a full header suite (CSP/HSTS/nosniff/…)
for the HTML app. The API is a separate origin (Render) serving JSON **and
binary media** (signed image URLs the frontend loads via <img>). Those
responses carried no security headers, so this middleware adds the safe,
non-breaking subset:

- ``X-Content-Type-Options: nosniff`` — the important one: stops a browser
  MIME-sniffing a media/JSON response into something executable. Hardens
  the media-serving routes (and the flag-gated brand-asset upload path
  that stores a caller-provided content-type).
- ``X-Frame-Options: DENY`` — the API is never meant to be framed.
- ``Referrer-Policy: strict-origin-when-cross-origin`` — matches the web app.
- ``Strict-Transport-Security`` — Render is HTTPS-only. No ``includeSubDomains``
  / ``preload`` because the host lives under the shared ``onrender.com``
  apex; scoping it to this host keeps siblings unaffected.

Deliberately NOT set:
- ``Cross-Origin-Resource-Policy`` — would break the Vercel frontend loading
  images from this (different) origin.
- ``Content-Security-Policy`` — the API returns no HTML; a strict CSP adds
  no protection to JSON/images and risks surprises.

Implemented as pure ASGI (not BaseHTTPMiddleware) so it injects headers on
``http.response.start`` without buffering ``FileResponse`` media bodies.
Only sets a header when the route hasn't already set its own.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=63072000"),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in _HEADERS:
                    if key.decode() not in headers:
                        headers.append(key.decode(), value.decode())
            await send(message)

        await self.app(scope, receive, send_with_headers)
