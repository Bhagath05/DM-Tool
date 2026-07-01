"""SecurityHeadersMiddleware — adds the safe header subset without clobbering
a header a route set for itself."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from aicmo.middleware.security_headers import SecurityHeadersMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/own")
    def own() -> JSONResponse:
        # A route that sets its own value must win (setdefault semantics).
        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    return app


def test_adds_security_headers():
    r = TestClient(_app()).get("/ping")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age" in r.headers["strict-transport-security"]


def test_route_header_wins_over_default():
    r = TestClient(_app()).get("/own")
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    # The others are still applied.
    assert r.headers["x-content-type-options"] == "nosniff"
