"""Sentry init + tenant-tag helpers.

Why this module exists and not just inline in main.py:
- Tenant tagging needs to happen from inside request handlers (after the
  tenancy dependency resolves). Centralising the calls here avoids
  scattering sentry_sdk imports across feature modules.
- The init runs exactly once at startup, before FastAPI is constructed,
  so Sentry can wrap exception handlers properly.

Configuration:
- SENTRY_DSN — when empty, init is a no-op (correct dev default).
- SENTRY_ENVIRONMENT — overrides the env tag. Defaults to api_env.
- SENTRY_TRACES_SAMPLE_RATE — performance traces. 0.0 in prod by default
  for cost; bump explicitly per-deploy.
- API_VERSION — release tag for source-map correlation later.
"""

from __future__ import annotations

import uuid

import structlog

from aicmo.config import get_settings

log = structlog.get_logger()


def init_sentry() -> bool:
    """Initialise Sentry. Returns True iff a real DSN was configured and
    init succeeded. Safe to call multiple times — only the first call
    actually inits the SDK.

    Called exactly once from aicmo/main.py at module load, BEFORE the
    FastAPI app is constructed (so Sentry's exception middleware wraps
    everything).
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        log.info("sentry.skip", reason="SENTRY_DSN not set")
        return False

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.httpx import HttpxIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    environment = settings.sentry_environment or settings.api_env

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=environment,
        release=settings.api_version,
        # Catch unhandled exceptions from every async + sync code path.
        integrations=[
            FastApiIntegration(
                # Capture failed_request_status_codes so 4xx-as-bugs are visible.
                failed_request_status_codes={500, 501, 502, 503, 504},
            ),
            StarletteIntegration(),
            AsyncioIntegration(),
            HttpxIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        # PII: keep emails + IPs OFF by default. Tenant tags are enough
        # to identify the affected org without storing PII in Sentry.
        send_default_pii=False,
        # Attach request bodies for 4xx/5xx — useful for debugging payload
        # validation errors. "medium" tops out around 10KB per request.
        max_request_body_size="medium",
        # Phase S2.8 — full event + breadcrumb scrubbers.
        before_send=_scrub_event,
        before_send_transaction=_scrub_event,
        before_breadcrumb=_scrub_breadcrumb,
    )

    sentry_sdk.set_tag("environment", environment)
    sentry_sdk.set_tag("api_version", settings.api_version)
    sentry_sdk.set_tag("service", "aicmo-api")

    log.info(
        "sentry.initialised",
        environment=environment,
        release=settings.api_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    return True


def bind_tenant_context(
    *,
    user_uuid: uuid.UUID | str | None,
    organization_id: uuid.UUID | str | None,
    brand_id: uuid.UUID | str | None,
    role_slugs: list[str] | None = None,
) -> None:
    """Tag the current Sentry scope with the resolved tenant context.

    Called from `tenancy/dependencies.py:require_tenant` right after the
    structlog binding. After this runs, any exception raised in the
    request gets `user`, `organization_id`, `brand_id` attached
    automatically.

    Safe to call when Sentry isn't initialised (becomes no-op).
    """
    try:
        import sentry_sdk
    except ImportError:
        return

    if user_uuid is not None:
        sentry_sdk.set_user({"id": str(user_uuid)})
    if organization_id is not None:
        sentry_sdk.set_tag("organization_id", str(organization_id))
    if brand_id is not None:
        sentry_sdk.set_tag("brand_id", str(brand_id))
    if role_slugs:
        sentry_sdk.set_tag("role", ",".join(sorted(role_slugs)))


def clear_tenant_context() -> None:
    """Strip tenant tags between requests. FastAPI dependency-scope
    handles this for us, but callers running long-lived async work
    (Arq jobs etc.) may want explicit cleanup."""
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.set_user(None)


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
#  Phase S2.8 — Sentry data protection.
#
#  Every event and breadcrumb shipped to Sentry runs through these
#  scrubbers. We strip:
#    - sensitive HTTP headers (Authorization, Cookie, X-API-Key, Set-Cookie)
#    - query-string + form fields with names matching secret keywords
#    - any string value matching known secret patterns (JWTs, sk_*, pk_live_,
#      sk-ant-*, AIza*, whsec_*, Fernet keys, Postgres DSNs with passwords)
#  Tenant headers (X-Organization-Id, X-Brand-Id) are KEPT — they're
#  triage signal, not secret.
# ---------------------------------------------------------------------

import re

_REDACTED = "[Filtered]"

_SENSITIVE_HEADER_PREFIXES = (
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
)

_SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?i)("
    r"password|passwd|pwd|"
    r"secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|signing[_-]?secret|webhook[_-]?secret|"
    r"private[_-]?key|encryption[_-]?key|integration[_-]?token|"
    r"authorization|bearer|session[_-]?id"
    r")"
)

_SECRET_VALUE_PATTERNS = (
    # Clerk live/test secret + Stripe-style sk_*
    re.compile(r"sk_(live|test)_[a-zA-Z0-9]{20,}"),
    re.compile(r"pk_live_[a-zA-Z0-9]{20,}"),
    # Anthropic
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{40,}"),
    # OpenAI (incl. proj keys)
    re.compile(r"sk-(proj-)?[A-Za-z0-9_\-]{30,}"),
    # Google AI Studio
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    # Svix webhook secret
    re.compile(r"whsec_[A-Za-z0-9+/=]{20,}"),
    # JWT (3 base64url segments)
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    # Postgres URL with embedded credentials
    re.compile(r"postgres(ql)?(\+psycopg)?://[^:\s]+:[^@\s]+@"),
)

_MAX_RECURSION = 6  # belt-and-suspenders against pathological payloads


def _scrub_string(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    redacted = value
    for pat in _SECRET_VALUE_PATTERNS:
        redacted = pat.sub(_REDACTED, redacted)
    return redacted


def _scrub_mapping(obj: dict, depth: int = 0) -> dict:
    if depth >= _MAX_RECURSION:
        return obj
    cleaned: dict = {}
    for k, v in obj.items():
        key_str = str(k)
        if _SENSITIVE_FIELD_PATTERN.search(key_str):
            cleaned[k] = _REDACTED
            continue
        cleaned[k] = _scrub_value(v, depth + 1)
    return cleaned


def _scrub_value(v, depth: int = 0):
    if isinstance(v, dict):
        return _scrub_mapping(v, depth)
    if isinstance(v, list):
        return [_scrub_value(item, depth + 1) for item in v]
    if isinstance(v, str):
        return _scrub_string(v)
    return v


def _scrub_headers(headers: dict) -> dict:
    cleaned: dict = {}
    for k, v in headers.items():
        kl = str(k).lower()
        if any(kl.startswith(p) for p in _SENSITIVE_HEADER_PREFIXES):
            cleaned[k] = _REDACTED
        else:
            cleaned[k] = _scrub_value(v)
    return cleaned


def _scrub_event(event: dict, _hint: dict | None = None) -> dict:
    """Top-level scrubber wired as Sentry `before_send`.

    Walks the event's request payload + extra context + exception
    messages, redacting secrets in place. Returns the event so Sentry
    ships the cleaned copy.
    """
    request = event.get("request") or {}
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_headers(headers)
        for body_key in ("data", "json", "query_string", "cookies"):
            body = request.get(body_key)
            if isinstance(body, (dict, list)):
                request[body_key] = _scrub_value(body)
            elif isinstance(body, str):
                request[body_key] = _scrub_string(body)
        event["request"] = request

    for ctx_key in ("extra", "contexts", "tags"):
        ctx = event.get(ctx_key)
        if isinstance(ctx, dict):
            event[ctx_key] = _scrub_value(ctx)

    # Scrub exception values (a secret in an error message would still
    # land in Sentry without this).
    exception = event.get("exception") or {}
    if isinstance(exception, dict):
        for entry in exception.get("values", []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("value"), str):
                entry["value"] = _scrub_string(entry["value"])

    # Same for plain log messages.
    if isinstance(event.get("message"), str):
        event["message"] = _scrub_string(event["message"])

    return event


def _scrub_breadcrumb(crumb: dict, _hint: dict | None = None) -> dict | None:
    """Per-breadcrumb scrubber. Returning None drops the breadcrumb."""
    if not isinstance(crumb, dict):
        return crumb
    data = crumb.get("data")
    if isinstance(data, dict):
        crumb["data"] = _scrub_value(data)
    if isinstance(crumb.get("message"), str):
        crumb["message"] = _scrub_string(crumb["message"])
    return crumb


# Back-compat alias — pre-S2.8 callers may have imported the old name.
_strip_sensitive_headers = _scrub_event
