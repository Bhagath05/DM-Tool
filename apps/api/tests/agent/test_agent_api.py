"""Phase 2 — agent API wiring + auth boundary.

Route/middleware wiring is checked without Postgres; the unauthenticated-401
assertion is Postgres-gated (same convention as the other auth integration
tests, which need a DB to resolve the session).
"""

from __future__ import annotations

import httpx
import pytest

_ORIGIN = "https://dm-tool-web.vercel.app"


def _client() -> httpx.AsyncClient:
    from aicmo.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://testserver",
        headers={"origin": _ORIGIN},
    )


def test_agent_routes_registered():
    from aicmo.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/agent/conversations" in paths
    assert "/api/v1/agent/conversations/{conversation_id}/messages" in paths


def test_security_and_rate_limit_middleware_active():
    from aicmo.main import app
    from aicmo.middleware.rate_limit import RateLimitMiddleware
    from aicmo.middleware.request_id import RequestIDMiddleware

    classes = {mw.cls for mw in app.user_middleware}
    assert RateLimitMiddleware in classes  # rate limiting applies to /agent too
    assert RequestIDMiddleware in classes  # request id available for audit


@pytest.mark.asyncio
async def test_agent_endpoints_require_auth():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    async with _client() as c:
        # No session cookie → no anonymous access, no demo bypass.
        r = await c.post("/api/v1/agent/conversations", json={})
        assert r.status_code == 401
        r = await c.get("/api/v1/agent/conversations")
        assert r.status_code == 401
        cid = "00000000-0000-0000-0000-000000000000"
        r = await c.post(f"/api/v1/agent/conversations/{cid}/messages", json={"content": "hi"})
        assert r.status_code == 401
