"""AUTH_MODE flag — tests for the demo-vs-clerk switch.

Pins the contract:
  - AUTH_MODE=demo: require_user returns the stable demo user without
    consulting headers or Clerk
  - AUTH_MODE=clerk + no Authorization: 401
  - AUTH_MODE=clerk + bad JWT: 401
  - AUTH_MODE=clerk + Clerk unconfigured: refuses to boot
  - AUTH_MODE=demo + Clerk unconfigured: boots fine (the whole point)
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


def _reload_clerk_with(monkeypatch: pytest.MonkeyPatch, **env: str):
    """Reload the clerk module under fresh env so module-level `settings`
    captures the new auth_mode / clerk_* values."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from aicmo.config import get_settings

    get_settings.cache_clear()
    import aicmo.auth.clerk as clerk_mod

    importlib.reload(clerk_mod)
    return clerk_mod


# ---------------------------------------------------------------------
#  AUTH_MODE=demo
# ---------------------------------------------------------------------


class TestDemoMode:
    @pytest.mark.asyncio
    async def test_returns_demo_user_with_no_authorization(self, monkeypatch):
        clerk = _reload_clerk_with(monkeypatch, AUTH_MODE="demo")
        ctx = await clerk.require_user(authorization=None)
        assert ctx.user_id == clerk.DEMO_USER_CLERK_ID
        assert ctx.claims.get("auth_mode") == "demo"

    @pytest.mark.asyncio
    async def test_ignores_authorization_header(self, monkeypatch):
        """Even a malformed Authorization header is ignored in demo mode —
        we never try to verify it."""
        clerk = _reload_clerk_with(monkeypatch, AUTH_MODE="demo")
        ctx = await clerk.require_user(authorization="Bearer not.a.real.jwt")
        assert ctx.user_id == clerk.DEMO_USER_CLERK_ID

    def test_startup_assert_passes_without_clerk(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="demo",
            CLERK_JWT_ISSUER="",
            CLERK_JWKS_URL="",
        )
        # Should NOT raise — demo mode is fine without Clerk.
        clerk.assert_auth_config_valid()


# ---------------------------------------------------------------------
#  AUTH_MODE=clerk
# ---------------------------------------------------------------------


class TestClerkMode:
    @pytest.mark.asyncio
    async def test_missing_authorization_returns_401(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="clerk",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        with pytest.raises(HTTPException) as exc:
            await clerk.require_user(authorization=None)
        assert exc.value.status_code == 401
        assert "Missing bearer token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_non_bearer_authorization_returns_401(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="clerk",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        with pytest.raises(HTTPException) as exc:
            await clerk.require_user(authorization="Basic dXNlcjpwYXNz")
        assert exc.value.status_code == 401

    def test_startup_assert_refuses_without_clerk_config(self, monkeypatch):
        """AUTH_MODE=clerk + no Clerk env → process refuses to start.
        This is the single defence against accidentally shipping a
        clerk-mode deploy that silently lets everything through."""
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="clerk",
            CLERK_JWT_ISSUER="",
            CLERK_JWKS_URL="",
        )
        with pytest.raises(SystemExit) as exc:
            clerk.assert_auth_config_valid()
        msg = str(exc.value)
        assert "AUTH_MODE='clerk'" in msg or "AUTH_MODE=\"clerk\"" in msg
        assert "Clerk is not configured" in msg

    def test_startup_assert_passes_with_real_clerk(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="clerk",
            CLERK_JWT_ISSUER="https://real-instance.clerk.dev",
            CLERK_JWKS_URL="https://real-instance.clerk.dev/.well-known/jwks.json",
        )
        clerk.assert_auth_config_valid()  # should not raise


# ---------------------------------------------------------------------
#  AUTH_MODE=hybrid — both demo + Clerk active
# ---------------------------------------------------------------------


class TestHybridMode:
    """Hybrid mode lets anonymous visitors hit the dashboard (demo-user)
    AND lets signed-in users authenticate via Clerk in the same deploy.
    """

    @pytest.mark.asyncio
    async def test_no_authorization_returns_demo_user(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        ctx = await clerk.require_user(authorization=None)
        assert ctx.user_id == clerk.DEMO_USER_CLERK_ID
        assert ctx.claims.get("auth_mode") == "hybrid-anonymous"

    @pytest.mark.asyncio
    async def test_empty_authorization_returns_demo_user(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        ctx = await clerk.require_user(authorization="")
        assert ctx.user_id == clerk.DEMO_USER_CLERK_ID

    @pytest.mark.asyncio
    async def test_non_bearer_authorization_returns_demo_user(self, monkeypatch):
        """In hybrid, a non-Bearer Authorization header is treated as
        "no token" → demo-user, NOT a 401. We only enforce token
        validity when the client explicitly sends a Bearer prefix."""
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        ctx = await clerk.require_user(authorization="Basic dXNlcjpwYXNz")
        assert ctx.user_id == clerk.DEMO_USER_CLERK_ID

    @pytest.mark.asyncio
    async def test_bearer_with_bad_jwt_returns_401(self, monkeypatch):
        """When a client DOES send a Bearer token, it must verify. We
        don't silently fall back to demo-user — that would let a buggy
        client hide auth failures behind the demo path."""
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="https://real.clerk.dev",
            CLERK_JWKS_URL="https://real.clerk.dev/.well-known/jwks.json",
        )
        # Stub the JWKS fetch so we don't hit the network; provide an
        # empty key set so JWT verification fails for any token.
        async def _fake_jwks(force: bool = False):
            return {"keys": []}

        monkeypatch.setattr(clerk, "_fetch_jwks", _fake_jwks)

        with pytest.raises(HTTPException) as exc:
            await clerk.require_user(
                authorization="Bearer eyJhbGciOiJSUzI1NiJ9.fake.signature"
            )
        assert exc.value.status_code == 401

    def test_startup_assert_refuses_without_clerk_config(self, monkeypatch):
        """Hybrid still requires Clerk env vars — without them, the
        Bearer-token branch would accept anything."""
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="",
            CLERK_JWKS_URL="",
        )
        with pytest.raises(SystemExit) as exc:
            clerk.assert_auth_config_valid()
        assert "AUTH_MODE='hybrid'" in str(exc.value)

    def test_startup_assert_passes_with_real_clerk(self, monkeypatch):
        clerk = _reload_clerk_with(
            monkeypatch,
            AUTH_MODE="hybrid",
            CLERK_JWT_ISSUER="https://real-instance.clerk.dev",
            CLERK_JWKS_URL="https://real-instance.clerk.dev/.well-known/jwks.json",
        )
        clerk.assert_auth_config_valid()  # should not raise


# ---------------------------------------------------------------------
#  Backwards-compat alias
# ---------------------------------------------------------------------


class TestBackwardsCompat:
    def test_old_assert_name_still_exists(self, monkeypatch):
        """Anything that still imports the old name keeps working."""
        clerk = _reload_clerk_with(monkeypatch, AUTH_MODE="demo")
        assert clerk.assert_clerk_for_non_dev is clerk.assert_auth_config_valid
