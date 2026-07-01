"""RequestIDMiddleware — generates/echoes X-Request-Id and binds it into the
structlog context so every log line for the request carries it."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.contextvars import get_contextvars

from aicmo.middleware.request_id import RequestIDMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ctx")
    def ctx() -> dict:
        # Read the structlog context mid-request — request_id must be bound.
        return {"bound": get_contextvars()}

    return TestClient(app)


def test_generates_and_binds_request_id():
    r = _client().get("/ctx")
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) == 32  # uuid4 hex
    assert r.json()["bound"].get("request_id") == rid


def test_echoes_valid_inbound_id():
    r = _client().get("/ctx", headers={"X-Request-Id": "abc-123_DEF.7"})
    assert r.headers["x-request-id"] == "abc-123_DEF.7"
    assert r.json()["bound"].get("request_id") == "abc-123_DEF.7"


def test_replaces_malformed_inbound_id():
    r = _client().get("/ctx", headers={"X-Request-Id": "bad id with spaces!"})
    assert r.headers["x-request-id"] != "bad id with spaces!"
    assert len(r.headers["x-request-id"]) == 32


def test_context_cleared_between_requests():
    c = _client()
    r1 = c.get("/ctx")
    r2 = c.get("/ctx")
    # Distinct ids, and no leakage of the previous request's context.
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]
    assert set(r2.json()["bound"].keys()) == {"request_id"}
