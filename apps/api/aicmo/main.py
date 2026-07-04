import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Force provider self-registration into IntegrationRegistry at import.
import aicmo.modules.integrations.providers  # noqa: F401
from aicmo.auth.clerk import require_user
from aicmo.config import get_settings
from aicmo.db.session import dispose_engine
from aicmo.modules.ads.router import router as ads_router
from aicmo.modules.advisor.router import router as advisor_router
from aicmo.modules.analytics.router import router as analytics_router
from aicmo.modules.autonomy.router import router as autonomy_router
from aicmo.modules.billing.router import (
    public_router as billing_public_router,
)
from aicmo.modules.billing.router import (
    router as billing_router,
)
from aicmo.modules.brands.router import brand_router
from aicmo.modules.brands.router import org_router as brands_org_router
from aicmo.modules.bundles.router import router as bundles_router
from aicmo.modules.campaigns.router import router as campaigns_router
from aicmo.modules.coach.router import router as coach_router
from aicmo.modules.competitors.router import router as competitors_router
from aicmo.modules.content.ops_router import router as content_ops_router
from aicmo.modules.content.router import router as content_router
from aicmo.modules.context.router import router as context_router
from aicmo.modules.creative.storage.base import MediaPersistenceUnavailable
from aicmo.modules.decision_engine.router import router as decision_engine_router
from aicmo.modules.insights.router import router as insights_router
from aicmo.modules.integrations.router import (
    public_router as integrations_public_router,
)
from aicmo.modules.integrations.router import (
    router as integrations_router,
)
from aicmo.modules.landing_pages.router import public_router as landing_pages_public_router
from aicmo.modules.landing_pages.router import router as landing_pages_router
from aicmo.modules.leads.router import public_router as leads_public_router
from aicmo.modules.leads.router import router as leads_router
from aicmo.modules.learning.router import router as learning_router
from aicmo.modules.notifications.router import router as notifications_router
from aicmo.modules.onboarding.router import router as onboarding_router
from aicmo.modules.operations.router import router as operations_router
from aicmo.modules.opportunities.router import router as opportunities_router
from aicmo.modules.orchestrator.router import router as orchestrator_router
from aicmo.modules.orgs.router import router as orgs_router
from aicmo.modules.performance.router import router as performance_router
from aicmo.modules.planner.router import router as planner_router
from aicmo.modules.poster.router import router as poster_router
from aicmo.modules.publishing.router import router as publishing_router
from aicmo.modules.rbac.router import catalog_router as rbac_catalog_router
from aicmo.modules.rbac.router import org_router as rbac_org_router
from aicmo.modules.security.router import (
    public_router as security_public_router,
)
from aicmo.modules.security.router import (
    router as security_router,
)
from aicmo.modules.social.router import router as social_router
from aicmo.modules.strategist.router import router as strategist_router
from aicmo.modules.team.router import (
    public_router as team_public_router,
)
from aicmo.modules.team.router import (
    router as team_router,
)
from aicmo.modules.trends.router import router as trends_router
from aicmo.modules.users.router import router as users_router
from aicmo.modules.visuals.media_router import public_router as media_public_router
from aicmo.modules.visuals.router import router as visuals_router

settings = get_settings()

# ---------------------------------------------------------------------
# SECURITY GUARD — fail fast if AUTH_MODE=clerk but Clerk isn't wired.
#
# The demo-user auth bypass exists for the public-demo product flow.
# If AUTH_MODE=clerk but Clerk env vars are missing, every request
# would silently become the demo-user → data leak. assert_auth_config_valid()
# raises SystemExit before uvicorn binds the port if that happens.
# Do not move this lower in the file; it must run at module load.
# ---------------------------------------------------------------------
from aicmo.auth.clerk import assert_auth_config_valid  # noqa: E402
from aicmo.config import validate_production_secrets  # noqa: E402

assert_auth_config_valid()
# Second boot gate: in production, refuse to start with placeholder
# secrets (the deploy never copied real values over .env.example).
# No-op in dev/staging so the demo flow keeps working.
validate_production_secrets(settings)

# ---------------------------------------------------------------------
# Sentry init MUST happen before FastAPI is constructed so its
# integrations can wrap exception handlers + middleware. No-op when
# SENTRY_DSN is empty (dev default).
# ---------------------------------------------------------------------
from aicmo.observability import init_sentry  # noqa: E402

init_sentry()

logging.basicConfig(level=settings.api_log_level)
structlog.configure(
    processors=[
        # Surface contextvars (request_id from the middleware; user/org/brand/
        # role bound by the tenant resolver) into every log line. Without this
        # those bound fields never reach the output.
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.api_log_level)
    ),
)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", env=settings.api_env)
    # Phase 0 — open one ARQ redis pool for the process so request
    # handlers can enqueue tenant-scoped jobs. Optional + guarded: if
    # Redis is unavailable, the web app still serves (enqueue degrades to
    # a logged no-op). Never let job infra block the API from booting.
    app.state.arq_pool = None
    if settings.jobs_enabled:
        try:
            from arq import create_pool

            from aicmo.queue.worker import WorkerSettings

            app.state.arq_pool = await create_pool(WorkerSettings.redis_settings)
            log.info("jobs.pool.ready")
        except Exception as e:
            log.warning("jobs.pool.unavailable", error=str(e))
    yield
    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
    await dispose_engine()
    log.info("api.shutdown")


app = FastAPI(
    title="AI-CMO API",
    version="0.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase S1.4 — global per-IP rate limit. Mounted AFTER CORS so OPTIONS
# preflights are answered by CORSMiddleware without consuming a token.
from aicmo.middleware.rate_limit import RateLimitMiddleware  # noqa: E402

app.add_middleware(RateLimitMiddleware)

# Security response headers (nosniff / frame-options / referrer / HSTS) on
# every API + media response. Safe subset — see the module docstring for
# what is deliberately omitted so cross-origin media loading keeps working.
from aicmo.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402

app.add_middleware(SecurityHeadersMiddleware)

# Request-id correlation. Mounted LAST so it is the OUTERMOST layer — the id
# is bound into structlog contextvars before any other middleware or route
# dependency runs, and echoed as X-Request-Id on the way out.
from aicmo.middleware.request_id import RequestIDMiddleware  # noqa: E402

app.add_middleware(RequestIDMiddleware)


@app.exception_handler(MediaPersistenceUnavailable)
async def _media_persistence_handler(
    _request: Request, exc: MediaPersistenceUnavailable
) -> JSONResponse:
    """Map a refused write (local disk in production) to a clear 409 instead
    of a 500. Any file-producing workflow (image generation, asset export)
    hits this when object storage isn't configured; non-file workflows are
    never affected because they never call the storage backend."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": (
                "Object storage isn't configured, so this feature is disabled. "
                "An admin must set MEDIA_BACKEND to a durable store (e.g. R2) "
                "before image generation and asset exports can be used."
            ),
            "code": "object_storage_required",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness — process is up. Cheap, never touches dependencies."""
    return {"status": "ok", "env": settings.api_env}


@app.get("/api/v1/system/storage")
async def system_storage(_auth=Depends(require_user)) -> dict[str, object]:
    """Storage capability for the frontend. Drives the admin-only notice +
    disabling of image-generation / export controls when durable object
    storage isn't configured. Auth-required, config-derived only (no tenant
    data); the admin-gating of the message itself happens client-side."""
    s = get_settings()
    return {
        "media_backend": s.media_backend,
        "environment": s.api_env,
        "media_persistence_available": s.media_persistence_available,
        # Features that write files stay off until persistence is available.
        "image_generation_enabled": s.media_persistence_available,
        "asset_exports_enabled": s.media_persistence_available,
    }


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness (P0-5) — validates PostgreSQL + Redis + the job queue.
    Returns 503 when a hard dependency (DB or Redis) is down so a load
    balancer / uptime monitor stops routing to this instance."""
    from aicmo.observability.health import readiness

    ok, report = await readiness()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "degraded", "checks": report},
    )


app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(trends_router, prefix="/api/v1")
# Phase 6.2B — ops routes (literal paths) BEFORE the base router so
# /content/folders + /content/search aren't captured as /content/{content_id}.
app.include_router(content_ops_router, prefix="/api/v1")
app.include_router(content_router, prefix="/api/v1")
app.include_router(ads_router, prefix="/api/v1")
app.include_router(visuals_router, prefix="/api/v1")
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(landing_pages_router, prefix="/api/v1")
app.include_router(leads_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(coach_router, prefix="/api/v1")
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(advisor_router, prefix="/api/v1")
app.include_router(competitors_router, prefix="/api/v1")
app.include_router(strategist_router, prefix="/api/v1")
app.include_router(planner_router, prefix="/api/v1")
app.include_router(decision_engine_router, prefix="/api/v1")
app.include_router(context_router, prefix="/api/v1")
app.include_router(bundles_router, prefix="/api/v1")
app.include_router(social_router, prefix="/api/v1")
app.include_router(poster_router, prefix="/api/v1")
app.include_router(learning_router, prefix="/api/v1")
app.include_router(insights_router, prefix="/api/v1")
app.include_router(orchestrator_router, prefix="/api/v1")
app.include_router(autonomy_router, prefix="/api/v1")
app.include_router(operations_router, prefix="/api/v1")
# Phase 9.1 — Performance Intelligence Engine (CSV-only ingest + diagnostics).
app.include_router(performance_router, prefix="/api/v1")
app.include_router(publishing_router, prefix="/api/v1")
# Phase 10.2a — Integration framework. Authenticated routes + the
# OAuth callback (public — verified by the signed state token, not
# tenant headers).
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(integrations_public_router, prefix="/api/v1")
# Phase 10.2b — Notification preferences (per-user, per-org matrix).
# No delivery dispatcher yet — channels report delivery_status='placeholder'.
app.include_router(notifications_router, prefix="/api/v1")
# Phase 10.2c — Security backend: session inventory, audit trail, revoke,
# Clerk webhook receiver. Public router is the Svix-verified webhook —
# never carries an Authorization header.
app.include_router(security_router, prefix="/api/v1")
app.include_router(security_public_router, prefix="/api/v1")
# Phase 10.2d — Team management: invite system + role catalog + team
# overview. Public router is /invites/* (auth required, no tenant header).
app.include_router(team_router, prefix="/api/v1")
app.include_router(team_public_router, prefix="/api/v1")
# Phase 10.2e — Billing backend (no Stripe yet). Plan catalog + lazy-
# provisioned Early Access subscriptions + usage summary + honest-
# placeholder upgrade-request flow.
app.include_router(billing_router, prefix="/api/v1")
# Phase 1 — Stripe webhook (public, signature-verified, no tenant header).
app.include_router(billing_public_router, prefix="/api/v1")
# Creative Core V0 — unified Creative Platform (video subsystem). Endpoints
# are flag-gated (409 when video_enabled=false). Public media router serves
# signed creative files.
from aicmo.modules.creative.router import (  # noqa: E402
    public_router as creative_public_router,
)
from aicmo.modules.creative.router import (
    router as creative_router,
)

app.include_router(creative_router, prefix="/api/v1")
app.include_router(creative_public_router, prefix="/api/v1")

# Phase 6.3 — AI Creative Brief (grounded in business/strategy/campaign/content).
from aicmo.modules.creative.brief_router import router as creative_brief_router  # noqa: E402

app.include_router(creative_brief_router, prefix="/api/v1")

# Phase 6.5 — CRM core (pipelines, stages, deals + grounded AI next-action).
from aicmo.modules.crm.router import router as crm_router  # noqa: E402

app.include_router(crm_router, prefix="/api/v1")

# Creative Studio (CS1) — the outcome layer + editable design model. Both
# flag-gated behind studio_enabled (409 when off), so they ship dark.
from aicmo.modules.creative.design.router import router as design_router  # noqa: E402
from aicmo.modules.growth.router import router as growth_router  # noqa: E402

app.include_router(growth_router, prefix="/api/v1")
app.include_router(design_router, prefix="/api/v1")
# SaaS foundation — identity, tenancy, RBAC. Mounted at /api/v1 alongside everything else.
app.include_router(users_router, prefix="/api/v1")
app.include_router(orgs_router, prefix="/api/v1")
app.include_router(brands_org_router, prefix="/api/v1")
app.include_router(brand_router, prefix="/api/v1")
app.include_router(rbac_catalog_router, prefix="/api/v1")
# Observability debug endpoints — mounted in dev/staging only.
if settings.api_env != "production":
    from aicmo.observability.router import router as debug_router
    app.include_router(debug_router, prefix="/api/v1")
app.include_router(rbac_org_router, prefix="/api/v1")
# Public surfaces — unauthenticated. Mounted under /api/v1 alongside auth'd
# routes to keep CORS and rate-limit policy consistent.
app.include_router(landing_pages_public_router, prefix="/api/v1")
app.include_router(leads_public_router, prefix="/api/v1")
app.include_router(media_public_router, prefix="/api/v1")
