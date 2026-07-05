"""CORS preflight — the Vercel frontend (whose per-deploy origin changes) must
be allowed to call the API; look-alike origins must not. Pins the regime that
unblocked the 'Couldn't load your workspace / Failed to fetch' production bug."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

from aicmo.config import get_settings


def _client() -> TestClient:
    """A minimal app carrying the SAME CORS config main.py applies."""
    settings = get_settings()
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/users/me")
    def _me():
        return {"ok": True}

    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/users/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-organization-id",
        },
    )


def test_vercel_deploy_origin_is_allowed():
    # The exact origin from the production failure screenshot.
    origin = "https://dm-tool-2ilhskuly-dmt-ool.vercel.app"
    r = _preflight(_client(), origin)
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_localhost_dev_origin_still_allowed():
    r = _preflight(_client(), "http://localhost:3000")
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_lookalike_origins_are_rejected():
    client = _client()
    for bad in ("https://evil.vercel.app", "https://dm-tool.evil.com"):
        r = _preflight(client, bad)
        # No allow-origin header echoed → browser blocks it.
        assert r.headers.get("access-control-allow-origin") is None, bad
