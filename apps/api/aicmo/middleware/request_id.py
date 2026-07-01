"""Per-request correlation id.

Binds a ``request_id`` into structlog's contextvars so every log line emitted
while handling a request carries it (the tenant resolver binds user/org/brand
the same way — both surface once ``merge_contextvars`` is in the processor
chain). Also echoes the id back as the ``X-Request-Id`` response header so a
customer/support ticket can reference a single request.

Honours an inbound ``X-Request-Id`` (e.g. from a load balancer / the frontend)
when present and well-formed, else generates one. Clears contextvars at the
start and end of each request so nothing leaks between requests sharing a
worker.

Pure ASGI (streaming-safe) and mounted OUTERMOST so the id is bound before any
other middleware or route dependency runs.
"""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = dict(scope["headers"]).get(b"x-request-id")
        candidate = inbound.decode("latin-1") if inbound else ""
        request_id = candidate if _SAFE_ID.match(candidate) else uuid.uuid4().hex

        clear_contextvars()
        bind_contextvars(request_id=request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_contextvars()
