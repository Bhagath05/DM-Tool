"""First-party auth — end-to-end through the real ASGI app (real Postgres).

Exercises the browser contract: signup → verify → signin (HttpOnly cookie) →
authenticated call → CSRF-guarded logout → rejected. Also pins the security
boundaries (unauthenticated 401, cross-origin 403, missing CSRF 403, no token
in the response body).
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from aicmo.auth.email import LogEmailSender, set_email_sender
from aicmo.config import get_settings
from tests._dbtest import pg_reachable

pytestmark = pytest.mark.asyncio

_ORIGIN = "http://localhost:3000"  # in the default CORS allowlist


class _CaptureSender:
    def __init__(self) -> None:
        self.links: list[str] = []

    async def send_verification(self, *, to: str, link: str) -> None:
        self.links.append(link)

    async def send_password_reset(self, *, to: str, link: str) -> None:
        self.links.append(link)


def _client() -> httpx.AsyncClient:
    from aicmo.main import app

    # https base URL so httpx's cookie jar stores + returns the Secure session
    # cookie (production issues Secure cookies; over http the jar would drop it).
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://testserver",
        headers={"origin": _ORIGIN},
    )


async def test_full_auth_flow_signup_verify_signin_logout():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    cap = _CaptureSender()
    set_email_sender(cap)
    email = f"e2e-{uuid.uuid4().hex[:12]}@example.com"
    pw = "a-strong-password-1"
    try:
        async with _client() as c:
            # Signup — generic 200, no existence disclosure.
            r = await c.post("/api/v1/auth/signup", json={"email": email, "password": pw})
            assert r.status_code == 200
            assert "verification" in r.json()["message"].lower()

            # Cannot sign in before verifying.
            r = await c.post("/api/v1/auth/signin", json={"email": email, "password": pw})
            assert r.status_code == 401

            # Verify via the emailed token.
            token = cap.links[-1].split("token=", 1)[1]
            r = await c.post("/api/v1/auth/verify-email", json={"token": token})
            assert r.status_code == 200

            # Sign in — sets HttpOnly session cookie + CSRF cookie.
            r = await c.post("/api/v1/auth/signin", json={"email": email, "password": pw})
            assert r.status_code == 200
            body = r.json()
            assert body["email"] == email
            # No secret material in the response body.
            assert "token" not in body and "password" not in str(body).lower()
            set_cookie = r.headers.get("set-cookie", "")
            assert settings.session_cookie_name in set_cookie
            assert "httponly" in set_cookie.lower()
            # The session cookie is held by the client jar now.
            assert settings.session_cookie_name in c.cookies

            # Authenticated call resolves the user.
            r = await c.get("/api/v1/auth/session")
            assert r.status_code == 200
            assert r.json()["email"] == email

            # /me (auth → tenant bootstrap) never 4xx for an authed user.
            r = await c.get("/api/v1/users/me")
            assert r.status_code == 200

            # Logout requires CSRF: without the header → 403.
            r = await c.post("/api/v1/auth/signout")
            assert r.status_code == 403

            # With the double-submit CSRF header → 200.
            csrf = c.cookies.get(settings.csrf_cookie_name)
            r = await c.post("/api/v1/auth/signout", headers={settings.csrf_header_name: csrf})
            assert r.status_code == 200

            # Session is revoked → authenticated call now 401.
            r = await c.get("/api/v1/auth/session")
            assert r.status_code == 401
    finally:
        set_email_sender(LogEmailSender())


async def test_unauthenticated_request_is_401():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    async with _client() as c:
        r = await c.get("/api/v1/auth/session")
        assert r.status_code == 401
        r = await c.get("/api/v1/users/me")
        assert r.status_code == 401


async def test_cross_origin_signin_rejected():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/signin",
            json={"email": "x@example.com", "password": "y"},
            headers={"origin": "https://evil.example.com"},
        )
        assert r.status_code == 403  # require_same_origin


async def test_password_reset_revokes_session_end_to_end():
    if not pg_reachable():
        pytest.skip("Postgres not reachable")
    settings = get_settings()
    cap = _CaptureSender()
    set_email_sender(cap)
    email = f"reset-{uuid.uuid4().hex[:12]}@example.com"
    pw = "original-password-1"
    try:
        async with _client() as c:
            await c.post("/api/v1/auth/signup", json={"email": email, "password": pw})
            token = cap.links[-1].split("token=", 1)[1]
            await c.post("/api/v1/auth/verify-email", json={"token": token})
            await c.post("/api/v1/auth/signin", json={"email": email, "password": pw})
            # Authenticated.
            assert (await c.get("/api/v1/auth/session")).status_code == 200

            # Request + perform a reset.
            await c.post("/api/v1/auth/request-password-reset", json={"email": email})
            reset_token = cap.links[-1].split("token=", 1)[1]
            r = await c.post(
                "/api/v1/auth/reset-password",
                json={"token": reset_token, "new_password": "brand-new-pass-9"},
            )
            assert r.status_code == 200

            # The old session was revoked by the reset.
            assert (await c.get("/api/v1/auth/session")).status_code == 401

            # Old password no longer works; new one does.
            r = await c.post("/api/v1/auth/signin", json={"email": email, "password": pw})
            assert r.status_code == 401
            r = await c.post(
                "/api/v1/auth/signin",
                json={"email": email, "password": "brand-new-pass-9"},
            )
            assert r.status_code == 200
    finally:
        set_email_sender(LogEmailSender())
