"""Global per-IP rate limiting middleware.

Phase S1.4 — applies to every /api/* request not on the skip list.
Reuses the existing Postgres fixed-window limiter so we stay on one
mechanism for the whole app (leads service already uses the same
`security.rate_limit.consume()`).

Why per-IP and not per-user:
- We don't want middleware to verify JWTs (latency + duplication of
  what require_user already does). IP is the cheap pre-auth signal,
  applied uniformly to anonymous traffic AND authenticated traffic.
- Authenticated abuse vectors are caught by the second per-user
  bucket inside require_permission once available; tracked for S3.

Scope buckets:
- "general"  — 300/min per IP, covers all /api/v1/* not in another scope.
- "gen"      — 60/min per IP, covers AI generation routes (ads/content/
                visuals/opportunities/bundles/coach/campaigns generate).
                These are expensive on LLM cost and most worth throttling.
- "public"   — 30/min per IP, covers public unauthenticated routes
                (landing pages, lead capture endpoints).

The leads capture endpoint already calls rate_limit.consume() with its
own bucket key (hashed-IP) — that's a second tighter check on top of
the middleware's "public" bucket, intentional defence in depth.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

import structlog
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aicmo.config import get_settings
from aicmo.db.session import SessionLocal
from aicmo.security import rate_limit

log = structlog.get_logger()

# Paths that bypass the limiter entirely. Health checks must always
# respond — the orchestrator uses them to decide pod liveness. The
# Sentry tunnel route handles its own backpressure.
_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/monitoring",
        "/favicon.ico",
    }
)

# Path prefix → scope. First match wins.
# Order matters: more specific prefixes first.
_SCOPE_RULES: tuple[tuple[str, str], ...] = (
    ("/api/v1/ads/generate", "gen"),
    ("/api/v1/content/generate", "gen"),
    ("/api/v1/visuals/render", "gen"),
    ("/api/v1/visuals/generate", "gen"),
    ("/api/v1/campaigns/generate", "gen"),
    ("/api/v1/opportunities/generate", "gen"),
    ("/api/v1/bundles/generate", "gen"),
    ("/api/v1/coach/generate", "gen"),
    ("/api/v1/landing-pages/public", "public"),
    ("/api/v1/leads/public", "public"),
    ("/api/v1/leads/capture", "public"),
    ("/api/v1/integrations/oauth/callback", "public"),
    ("/api/v1/security/webhooks/", "public"),
    ("/api/v1/", "general"),
)

# Per-minute limit by scope.
_LIMITS_BY_SCOPE: dict[str, int] = {
    "gen": 60,
    "general": 300,
    "public": 30,
}


def _classify(path: str) -> str | None:
    """Return scope for the path, or None if exempt."""
    if path in _SKIP_PATHS:
        return None
    for prefix, scope in _SCOPE_RULES:
        if path.startswith(prefix):
            return scope
    # Non-API routes (e.g. /docs, /openapi.json) aren't rate-limited.
    return None


def _client_ip(request: Request) -> str:
    """Pull the originating IP for rate-limiting.

    Phase 5.1/5.9 hardening: X-Forwarded-For is client-appendable, so the
    LEFTMOST entry is attacker-spoofable — a client can send
    `X-Forwarded-For: <random>` to mint a fresh limiter bucket per request and
    evade throttling (or frame an arbitrary IP). We instead read the entry
    `trusted_proxy_hops` positions from the RIGHT: proxies APPEND the address
    they received from, so the rightmost entries are the ones OUR trusted proxy
    added and cannot be forged by the client. Only trusted when behind a proxy
    (api_env != development)."""
    settings = get_settings()
    if settings.api_env != "development":
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                hops = max(1, settings.trusted_proxy_hops)
                # The client as seen by the closest trusted proxy. Falls back to
                # the leftmost only when the chain is shorter than expected.
                return parts[-hops] if hops <= len(parts) else parts[0]
    client = request.client
    return client.host if client else "unknown"


def _bucket_key(scope: str, ip: str) -> str:
    """Stable per-(scope, ip) key. Hash the IP for storage so the
    rate_limit_buckets table never holds raw IPs (GDPR)."""
    settings = get_settings()
    pepper = (settings.ip_hash_pepper or "dev-pepper").encode()
    ip_hash = hashlib.sha256(pepper + ip.encode()).hexdigest()[:16]
    return f"mw:{scope}:{ip_hash}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware — per-IP, per-scope fixed window."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        scope = _classify(request.url.path)
        if scope is None:
            return await call_next(request)

        ip = _client_ip(request)
        key = _bucket_key(scope, ip)
        limit = _LIMITS_BY_SCOPE[scope]

        # Open a dedicated session for the limiter so we don't share a
        # session lifecycle with the request handler. The UPSERT commits
        # before the handler runs.
        try:
            async with SessionLocal() as session:
                await rate_limit.consume(session, key=key, limit=limit)
        except HTTPException as exc:
            # consume() raised 429. Convert to a clean JSONResponse with
            # Retry-After so middleware doesn't fight FastAPI's exception
            # handler chain.
            if exc.status_code == 429:
                return JSONResponse(
                    status_code=429,
                    content={"detail": exc.detail, "scope": scope},
                    headers={"Retry-After": "60"},
                )
            raise
        except Exception as e:
            # If Postgres is down, fail open rather than 500 every request.
            # The leads service still has its own internal check on top.
            log.warning("rate_limit.middleware.error", error=str(e), path=request.url.path)

        return await call_next(request)
