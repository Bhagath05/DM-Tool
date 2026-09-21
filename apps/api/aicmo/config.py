from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_env: Literal["development", "staging", "production"] = "development"
    api_log_level: str = "INFO"
    api_cors_origins: str = "http://localhost:3000"
    # Vercel gives every deploy a fresh URL (dm-tool-<hash>-…​.vercel.app), so an
    # exact allow-list can't keep up. This regex allows this project's Vercel
    # origins (production + preview + per-deploy) in addition to `api_cors_origins`.
    # Scoped to `dm-tool*.vercel.app` — never a blanket `*.vercel.app`. Override
    # via API_CORS_ORIGIN_REGEX (empty string disables it).
    api_cors_origin_regex: str = r"^https://dm-tool[a-z0-9-]*\.vercel\.app$"

    # Phase 5.1/5.9 — number of trusted reverse-proxy hops in front of the app.
    # The client IP is taken this many entries from the RIGHT of X-Forwarded-For
    # (the entries closest to us are the ones our trusted proxy appended;
    # leftmost entries are attacker-spoofable). Render terminates with a single
    # proxy → 1. Increase only if you add a trusted CDN/WAF in front.
    trusted_proxy_hops: int = 1

    # --- First-party authentication (DM Tool is the system of record) ---
    # Authentication is first-party server-side sessions only — no Clerk, no
    # demo bypass, no JWT. There is intentionally no AUTH_MODE flag.
    # Session cookie. `secure` defaults on; local http dev sets
    # SESSION_COOKIE_SECURE=false. SameSite=lax is correct for a same-site
    # deploy (localhost:3000 → localhost:8000, or app + api under one domain);
    # a cross-site split (separate frontend/api domains) needs
    # SESSION_COOKIE_SAMESITE=none with secure=true.
    session_cookie_name: str = "dmt_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_domain: str = ""  # empty → host-only cookie
    session_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # Rotate the session token when a still-valid session is older than this
    # (defence against fixation / long-lived stolen tokens).
    session_rotate_after_seconds: int = 60 * 60 * 24  # 1 day
    # CSRF double-submit token. This cookie is NOT HttpOnly (the SPA reads it
    # and echoes it in a header); the session cookie stays HttpOnly.
    csrf_cookie_name: str = "dmt_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    # Single-use email token lifetimes.
    email_verify_ttl_seconds: int = 60 * 60 * 24  # 24h
    password_reset_ttl_seconds: int = 60 * 60  # 1h
    # Require a verified email before sign-in succeeds.
    auth_require_verified_email: bool = True
    # Login throttle (brute-force / credential-stuffing) — counted per account
    # and per source IP within a rolling window.
    login_attempt_window_seconds: int = 15 * 60
    login_max_attempts_per_account: int = 10
    login_max_attempts_per_ip: int = 50

    database_url: str = "postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo"
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_pool_recycle: int = Field(default=1800)
    redis_url: str = "redis://localhost:6379/0"

    @field_validator("database_url", mode="after")
    @classmethod
    def _force_async_psycopg3_driver(cls, v: str) -> str:
        """Normalise DATABASE_URL so SQLAlchemy always uses psycopg **v3**.

        Managed hosts (Render, Heroku, Railway) hand out a *driver-less* URL:
            postgres://...      or      postgresql://...
        SQLAlchemy maps the bare ``postgresql`` scheme to **psycopg2** — a sync
        driver that (a) isn't installed here (→ ``ModuleNotFoundError: psycopg2``
        at engine creation, before the app can even start) and (b) can't be used
        with ``create_async_engine`` anyway. We rewrite the scheme to
        ``postgresql+psycopg`` (psycopg v3, async-capable) so no manual URL
        editing is ever required in the dashboard.

        Already-qualified URLs are respected: ``postgresql+psycopg`` /
        ``postgresql+asyncpg`` pass through untouched; an explicit (and wrong)
        ``postgresql+psycopg2`` is upgraded to ``postgresql+psycopg``.
        """
        if v.startswith("postgres://"):  # legacy Heroku/Render scheme
            v = "postgresql://" + v.removeprefix("postgres://")
        if v.startswith("postgresql+psycopg2://"):
            return "postgresql+psycopg://" + v.removeprefix("postgresql+psycopg2://")
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v.removeprefix("postgresql://")
        return v

    # -----------------------------------------------------------------
    # Row-Level Security (RLS) — defense-in-depth tenant isolation at the
    # database layer, on top of the application-layer filters.
    #
    # OFF by default. When True, the tenant resolver sets the per-request
    # session GUCs (app.current_org_id / app.current_user_id) so the RLS
    # policies created by migration 0032 can enforce isolation.
    #
    # IMPORTANT: this flag only wires the *session context*. The policies
    # are dormant until RLS is ENABLED on the tables via
    # `scripts/rls_activate.py` (a deliberate, separate ops action).
    # Flipping this flag alone is a no-op unless activation has run; and
    # running activation without this flag would break reads. See
    # docs/database/RLS_ACTIVATION.md.
    # -----------------------------------------------------------------
    db_rls_enabled: bool = Field(default=False)

    # -----------------------------------------------------------------
    # Background jobs (ARQ). Master kill switch for enqueue. When false,
    # enqueue_tenant_job becomes a logged no-op — the web app is wholly
    # unaffected (no job currently gates any request path). Default true
    # so the harness works out of the box; flip to false to halt all
    # background dispatch without a deploy.
    # -----------------------------------------------------------------
    jobs_enabled: bool = Field(default=True)

    # -----------------------------------------------------------------
    # Billing (Stripe) — Phase 1. Both flags default OFF so the entire
    # billing-live path ships dormant; the product keeps its current
    # "honest placeholder" upgrade flow until enabled per-environment.
    #
    #   billing_live_enabled    — when true, /billing/checkout + /portal
    #                             talk to Stripe; the webhook syncs subs.
    #   billing_enforce_limits  — when true, the quota gate can BLOCK a
    #                             generation over the plan limit. Default
    #                             false = record-only (measure first).
    #
    # Plan prices + quotas live in the DB (plan / plan_quota tables), not
    # here — they are tunable without a deploy. Only the Stripe API
    # secrets live in config.
    # -----------------------------------------------------------------
    billing_live_enabled: bool = Field(default=False)
    billing_enforce_limits: bool = Field(default=False)
    stripe_secret_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")

    # Advisor engine — persistent recommendation memory + task lifecycle.
    advisor_engine_enabled: bool = Field(default=True)
    advisor_intelligence_enabled: bool = Field(default=True)
    advisor_outcome_learning_enabled: bool = Field(default=True)
    advisor_agent_enabled: bool = Field(default=True)
    connector_sync_enabled: bool = Field(default=True)

    # Autonomy master switch (Module 10 — Future Autonomy Flags). The platform-
    # wide kill-switch for AI auto-execution. Default OFF: even if a brand sets a
    # high autonomy level, no action auto-runs until this is explicitly enabled
    # per environment. Mirrors the video_enabled / billing_live_enabled pattern —
    # the ultimate guarantee that nothing executes automatically by default.
    autonomy_execution_enabled: bool = Field(default=False)

    # Phase 4 — Autonomous Operations Engine (continuous loop).
    # The loop is driven by a driver-agnostic service (`operations.driver`).
    # Today it's invoked by POST /operations/tick; tomorrow by the Arq worker
    # cron — same business logic. These knobs govern that loop.
    #   operations_tick_secret — shared secret the /operations/tick endpoint
    #     requires. Empty (default) → the endpoint is DISABLED (503), so the
    #     loop cannot be triggered until an operator sets a secret per env.
    #   operations_monitor_interval_seconds — per-brand cadence: a brand is only
    #     re-snapshotted after this many seconds (idempotency; repeated ticks are
    #     no-ops within the window).
    #   operations_tick_min_gap_seconds — global throttle between full cycles
    #     (rate-limit on the endpoint).
    operations_tick_secret: str = Field(default="")
    operations_monitor_interval_seconds: int = Field(default=300)
    operations_tick_min_gap_seconds: int = Field(default=20)

    # Phase 6.5 — CRM email platform. `email_provider` selects the send provider
    # (empty/"stub" = record-only, no delivery). `email_webhook_secret` gates the
    # provider event webhook (disabled until set). Neither fabricates delivery.
    #   email_provider="resend" + email_api_key + email_from → real delivery.
    email_provider: str = Field(default="")
    email_api_key: str = Field(default="")
    email_from: str = Field(default="")  # verified sender, e.g. "DM Tool <hi@x.com>"
    email_webhook_secret: str = Field(default="")

    # Phase 4.6 — the reasoning steps of the loop (Decision Engine + Learning
    # synthesis) cost LLM calls, so they're OFF by default. Cheap monitoring /
    # detection / scheduling always run; enable this to add the reasoning layer.
    # Cooldowns bound how often each engine runs per brand (cost control).
    # --- Phase 8: daily autonomous execution guardrails (Priority 3) ---
    #   The cycle runs once a day on the existing Arq worker. These are the
    #   ceilings the owner set; they are read by the cron + pipeline, and every
    #   one can be overridden per-environment without a deploy.
    #
    #   NOTE: `operations_pipeline_enabled` + `autonomy_execution_enabled` both
    #   default OFF. Until they are switched on the daily cycle only observes
    #   and detects — it never reasons, spends, or executes. Turning them on is
    #   a deliberate, billable decision.
    operations_daily_cron_enabled: bool = Field(default=True)
    operations_daily_cron_hour: int = Field(default=8, ge=0, le=23)
    operations_emergency_stop: bool = Field(default=False)
    operations_daily_budget_usd: float = Field(default=1.0, ge=0)
    operations_max_tasks_per_cycle: int = Field(default=10, ge=0)
    operations_max_reasoning_tasks: int = Field(default=5, ge=0)
    operations_max_content_tasks: int = Field(default=5, ge=0)
    operations_pipeline_enabled: bool = Field(default=False)
    operations_decision_cooldown_seconds: int = Field(default=21600)   # 6h
    operations_learning_cooldown_seconds: int = Field(default=86400)   # 24h

    # -----------------------------------------------------------------
    # Creative Platform / Video (Creative Core V0). Ships DARK:
    # `video_enabled=false` → every /creative/* endpoint returns 409 and
    # no pipeline runs, so the running product is unchanged. Providers +
    # storage default to no-network stubs/local — even if the flag were
    # flipped there is no external spend until V1 wires real adapters.
    #
    # Plan quotas + the creative_format catalog live in the DB (tunable
    # without deploy). Only provider secrets live here, and they are
    # required ONLY when video_enabled=true (boot-guarded).
    # -----------------------------------------------------------------
    video_enabled: bool = Field(default=False)
    video_default_provider: Literal["stub", "veo3", "slideshow"] = "stub"
    tts_default_provider: Literal["stub", "elevenlabs", "openai"] = "stub"
    # Storage provider, env-selected. "local" = disk (dev/staging only — see
    # media_persistence_available). "s3"/"r2" both use the S3-compatible
    # backend; "r2" is Cloudflare R2 via s3_endpoint_url. No provider is
    # hardcoded — selection is entirely by this env var.
    media_backend: Literal["local", "s3", "r2"] = "local"

    # -----------------------------------------------------------------
    # LinkedIn Poster Studio. Topic → branded announcement poster
    # (HTML/CSS composed → PNG) + long-form caption. Ships DARK
    # (`poster_enabled=false` → /poster/* returns 409). Rendering needs a
    # headless browser: Playwright if installed, else a Chrome/Chromium at
    # `poster_chrome_bin` / $POSTER_CHROME_BIN (auto-detected on common
    # paths). The AI hero (optional, per-request) reuses the image provider.
    # -----------------------------------------------------------------
    poster_enabled: bool = Field(default=False)
    poster_chrome_bin: str = Field(default="")

    # Creative Studio (CS1) ships DARK behind its own flag. When false,
    # every /api/v1/creative/designs/* and /api/v1/growth/* studio route
    # returns 409 and the Studio UI is hidden. Independent of video_enabled
    # so the editable-design spine can be turned on without enabling video.
    # No secrets — the studio reuses existing providers/storage/billing.
    studio_enabled: bool = Field(default=False)

    # Cost / abuse caps (video is expensive).
    video_render_daily_cap: int = Field(default=5)  # per user/day
    video_org_monthly_budget_cents: int = Field(default=0)  # 0 = use plan default

    # Provider secrets — required only when video_enabled=true.
    vertex_project: str = Field(default="")
    vertex_location: str = Field(default="us-central1")
    google_application_credentials: str = Field(default="")  # SA JSON path
    elevenlabs_api_key: str = Field(default="")
    s3_bucket: str = Field(default="")
    s3_region: str = Field(default="")
    s3_endpoint_url: str = Field(default="")  # S3-compatible (AWS/R2/MinIO)

    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")

    llm_default_provider: Literal["anthropic", "openai", "google"] = "openai"
    # Marketing Brain — GPT-5.6 Sol (API alias `gpt-5.6`). Overridable via
    # LLM_DEFAULT_MODEL. This is the canonical default so an unset env var
    # can never silently fall back to a weaker model.
    llm_default_model: str = "gpt-5.6"
    # Optional per-task provider/model map (Phase B). Empty = no overrides;
    # known tasks without an entry use the global defaults above.
    # Format: "task:provider/model,task2:provider/model"
    # Example: "business_research:google/gemini-2.5-flash,intelligence:openai/gpt-5.6"
    llm_task_models: str = Field(default="")

    @field_validator("llm_task_models", mode="after")
    @classmethod
    def _validate_llm_task_models(cls, v: str) -> str:
        """Fail closed on malformed LLM_TASK_MODELS at settings load."""
        from aicmo.llm.policy import parse_llm_task_models

        parse_llm_task_models(v)  # raises LLMTaskPolicyError on bad input
        return v

    # Lead-capture security
    turnstile_site_key: str = Field(default="")
    turnstile_secret_key: str = Field(default="")
    ip_hash_pepper: str = Field(default="")
    lead_capture_rate_limit: int = Field(default=5)
    public_base_url: str = Field(default="http://localhost:3000")

    # Phase 4-A — image rendering. Local-disk storage + HMAC-signed URLs.
    # When we outgrow disk volume we'll swap MEDIA_BACKEND for s3 — that's
    # the only line that needs to change for the migration.
    media_dir: str = Field(default="./media")
    media_signing_secret: str = Field(
        default="",
        description="HMAC key for signed media URLs. Required in production.",
    )
    image_render_daily_cap: int = Field(
        default=20,
        description="Per-user daily cap on image renders. Non-negotiable cost governance.",
    )
    image_default_provider: Literal["openai"] = "openai"

    # Phase Social-1 — read-only social intelligence credentials.
    # Without these set, the OAuth-based connection flow gracefully
    # falls back to "config needed" UX, and the manual-import path
    # remains the workable alternative.
    ig_client_id: str = Field(default="")
    ig_client_secret: str = Field(default="")

    # Google Business Profile OAuth — local business outcome signals.
    google_gbp_client_id: str = Field(default="")
    google_gbp_client_secret: str = Field(default="")

    # Facebook Pages OAuth — shares Meta app credentials with Instagram when
    # FB_* are unset (same developer console app).
    fb_client_id: str = Field(default="")
    fb_client_secret: str = Field(default="")

    # LinkedIn organic posting + metrics.
    linkedin_client_id: str = Field(default="")
    linkedin_client_secret: str = Field(default="")

    # YouTube channel OAuth (Google Cloud OAuth client).
    youtube_client_id: str = Field(default="")
    youtube_client_secret: str = Field(default="")

    # Pinterest organic pins.
    pinterest_app_id: str = Field(default="")
    pinterest_app_secret: str = Field(default="")

    # ---- Sentry (A2) ----
    # When SENTRY_DSN is empty, Sentry init is skipped — this is the
    # correct dev-default. Production deploys MUST set SENTRY_DSN +
    # SENTRY_ENVIRONMENT or errors will be invisible.
    sentry_dsn: str = Field(default="")
    sentry_environment: str = Field(
        default="",
        description="Sentry environment tag. Defaults to api_env when empty.",
    )
    # P0-4 — operational Slack alerts (worker failures, DB/Redis down). Empty
    # disables Slack (Sentry still receives everything). Incoming-webhook URL.
    slack_alert_webhook_url: str = Field(default="")
    # P1 — slow-query observability via pg_stat_statements. The monitor cron
    # reads mean-execution-time per statement; any statement whose mean exceeds
    # `slow_query_alert_ms` triggers a warning alert (top `slow_query_top_n`
    # offenders attached). Reading pg_stat_statements is a no-op when the
    # extension isn't installed — the monitor degrades gracefully.
    slow_query_alert_ms: float = Field(
        default=500.0,
        description="Mean per-statement execution time (ms) above which the monitor alerts.",
    )
    slow_query_top_n: int = Field(
        default=5,
        description="How many of the slowest statements to include in a slow-query alert.",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.0,
        description="Performance traces sample rate (0.0 disables). Keep low in prod for cost.",
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.0,
        description="Profiling sample rate (0.0 disables).",
    )
    api_version: str = Field(
        default="0.0.0",
        description="App version tag — attached to every Sentry event for release tracking.",
    )

    # -----------------------------------------------------------------
    # Phase 10.2a — Integration framework token encryption.
    #
    # `integration_token_key` is a base64-encoded Fernet key (44 chars).
    # Generate with: `python -c "from cryptography.fernet import Fernet;
    #                            print(Fernet.generate_key().decode())"`
    #
    # Required when any IntegrationProvider is connected. Until a
    # provider is implemented (Phase 11 lights up Meta), the key may
    # remain absent in dev — `assert_integration_key_present()` is
    # called lazily at the first connect/sync attempt, not at boot.
    # -----------------------------------------------------------------
    integration_token_key: str = Field(
        default="",
        description=(
            "Fernet key used to encrypt OAuth tokens at rest. Empty in "
            "dev is OK until a real connector is connected — the "
            "encryption layer fails loudly when actually used."
        ),
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        return self.api_cors_origin_regex.strip() or None

    @property
    def media_persistence_available(self) -> bool:
        """Whether generated assets can be stored durably.

        False ONLY when running in production on the `local` disk backend:
        Render's filesystem is ephemeral AND not shared between web/worker,
        so any file written there is lost on restart and unservable across
        services. In that state the production-safety gate keeps image
        generation + file exports DISABLED (text/strategy/edit/revision
        workflows are unaffected — they live in Postgres). Any durable
        backend (`s3`/`r2`), and any non-production env, returns True.

        Selection is purely env-driven: set MEDIA_BACKEND=r2 (+ R2 creds)
        and this flips to True with no code change.
        """
        if self.media_backend == "local" and self.api_env == "production":
            return False
        return True


# Placeholder substrings that .env.example uses. If validate_production_secrets()
# finds any of these in a production secret, it refuses to boot — the deploy
# never copied real values over the template.
_PLACEHOLDER_TOKENS = (
    "replace_me",
    "your-instance",
    "example.com",
    "changeme",
    "REPLACE_ME",
)


def _looks_like_placeholder(value: str) -> bool:
    if not value:
        return True
    return any(token in value for token in _PLACEHOLDER_TOKENS)


# Transactional email providers that actually deliver mail (mirrors
# aicmo.modules.crm.email_providers.get_email_provider). Empty/"stub" = the
# record-only dev adapter, which never delivers.
_SUPPORTED_EMAIL_PROVIDERS: frozenset[str] = frozenset({"resend"})


def email_delivery_configured(settings: "Settings") -> bool:
    """True iff a real transactional email provider is fully configured, so
    auth verification / password-reset emails are delivered rather than only
    written to the log. Drives both the production boot guard and the runtime
    sender selection so the two never disagree."""
    provider = (settings.email_provider or "").strip().lower()
    if provider not in _SUPPORTED_EMAIL_PROVIDERS:
        return False
    return bool((settings.email_api_key or "").strip()) and bool(
        (settings.email_from or "").strip()
    )


def validate_production_secrets(settings: "Settings") -> None:
    """Refuse to boot in production with placeholder / missing secrets.

    Runs from main.py at module load. No-op outside production — dev + staging
    stay unchanged so local development works with `replace_me` placeholders.
    """
    if settings.api_env != "production":
        return

    errors: list[str] = []

    # Auth posture: first-party session cookies MUST be Secure in production,
    # otherwise the session token can leak over plaintext HTTP.
    if not settings.session_cookie_secure:
        errors.append(
            "SESSION_COOKIE_SECURE must be true in production — a non-Secure "
            "session cookie can be sent over plaintext HTTP and stolen."
        )

    # Redis is a HARD production dependency: the Arq worker, the job queue,
    # and the response cache all use it. A missing REDIS_URL silently falls
    # back to the localhost default — so the queue is dead and every
    # scheduled/background job never runs, with no error at request time.
    # Turn that silent failure into a loud boot failure. (P-stab: this is the
    # exact misconfiguration the stabilization audit found in the wild.)
    redis = (settings.redis_url or "").strip()
    if not redis or "localhost" in redis or "127.0.0.1" in redis or "::1" in redis:
        errors.append(
            "REDIS_URL is missing or points at localhost. Production needs a "
            "real Redis instance — the background worker, job queue and cache "
            "all depend on it (set REDIS_URL to the managed Redis connection "
            "string)."
        )

    # Required secret bundles in prod. Each tuple is (env_name, value).
    required = [
        ("IP_HASH_PEPPER", settings.ip_hash_pepper),
        ("MEDIA_SIGNING_SECRET", settings.media_signing_secret),
        ("SENTRY_DSN", settings.sentry_dsn),
        # Required so OAuth tokens (social + integrations) are always
        # encrypted at rest in production (P0-2). Without it, the social
        # token layer would silently store plaintext.
        ("INTEGRATION_TOKEN_KEY", settings.integration_token_key),
    ]
    for name, value in required:
        if _looks_like_placeholder(value):
            errors.append(f"{name} is missing or a placeholder.")

    # Transactional email MUST be wired in production. With no provider the
    # verification / password-reset links only reach the logs, so real users
    # can never verify their address (and sign-in requires a verified email).
    # Fail closed rather than silently onboard accounts that can never sign in.
    if not email_delivery_configured(settings):
        errors.append(
            "Email delivery is not configured — set EMAIL_PROVIDER (e.g. 'resend') "
            "+ EMAIL_API_KEY + EMAIL_FROM so verification/reset emails are actually "
            "sent, not just logged."
        )

    # LLM providers — at least one real key must be set. Empty is fine if
    # the provider isn't in use, but the configured default provider's key
    # must be present.
    provider_keys = {
        "anthropic": ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        "openai": ("OPENAI_API_KEY", settings.openai_api_key),
        "google": ("GOOGLE_API_KEY", settings.google_api_key),
    }
    default_name, default_value = provider_keys[settings.llm_default_provider]
    if _looks_like_placeholder(default_value):
        errors.append(
            f"{default_name} is missing or a placeholder, but it is the configured "
            f"LLM_DEFAULT_PROVIDER. Set a real value or change the default provider."
        )

    # Stripe secrets are required ONLY when live billing is on — a prod
    # deploy that hasn't enabled billing still boots without them.
    if settings.billing_live_enabled:
        for name, value in (
            ("STRIPE_SECRET_KEY", settings.stripe_secret_key),
            ("STRIPE_WEBHOOK_SECRET", settings.stripe_webhook_secret),
        ):
            if _looks_like_placeholder(value):
                errors.append(
                    f"{name} is missing or a placeholder, but BILLING_LIVE_ENABLED "
                    "is true."
                )

    # Video/creative provider secrets required ONLY when video is enabled
    # AND a real (non-stub) provider/backend is selected. A video-off prod
    # deploy — and a video-on-but-stub one — still boots.
    if settings.video_enabled:
        if settings.video_default_provider == "veo3":
            for name, value in (
                ("VERTEX_PROJECT", settings.vertex_project),
                ("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials),
            ):
                if _looks_like_placeholder(value):
                    errors.append(f"{name} is missing, but VIDEO_DEFAULT_PROVIDER=veo3.")
        if settings.tts_default_provider == "elevenlabs" and _looks_like_placeholder(
            settings.elevenlabs_api_key
        ):
            errors.append("ELEVENLABS_API_KEY is missing, but TTS_DEFAULT_PROVIDER=elevenlabs.")
        if settings.media_backend in ("s3", "r2") and _looks_like_placeholder(
            settings.s3_bucket
        ):
            errors.append(
                f"S3_BUCKET is missing, but MEDIA_BACKEND={settings.media_backend}."
            )

    if errors:
        bullets = "\n  - ".join(errors)
        raise SystemExit(
            "FATAL: production environment has missing or placeholder secrets. "
            "Refusing to start.\n  - " + bullets +
            "\n\nSee docs/security/SECRETS.md for the rotation runbook."
        )


def validate_worker_secrets(settings: "Settings") -> None:
    """Fail closed at worker startup in production if the secrets the WORKER
    actually uses are missing.

    The worker serves no HTTP auth, so it needs neither CLERK_* nor
    IP_HASH_PEPPER (those gate the API's auth + lead-capture paths). It DOES
    need: the Redis broker, the DB, the OAuth-token encryption key (publishing
    jobs decrypt provider tokens), the media-signing secret (jobs mint signed
    media URLs), and the default LLM provider's key (advisor/operations/video
    jobs). No-op outside production. Raises with variable NAMES only — never
    values, connection strings, tokens, or keys.
    """
    if settings.api_env != "production":
        return

    missing: list[str] = []

    redis = (settings.redis_url or "").strip()
    if not redis or "localhost" in redis or "127.0.0.1" in redis or "::1" in redis:
        missing.append("REDIS_URL")

    db = (settings.database_url or "").strip()
    if not db or "localhost" in db or "127.0.0.1" in db or "::1" in db:
        missing.append("DATABASE_URL")

    for name, value in (
        ("INTEGRATION_TOKEN_KEY", settings.integration_token_key),
        ("MEDIA_SIGNING_SECRET", settings.media_signing_secret),
    ):
        if _looks_like_placeholder(value):
            missing.append(name)

    # The default LLM provider's key — whichever provider is selected.
    provider_keys = {
        "anthropic": ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        "openai": ("OPENAI_API_KEY", settings.openai_api_key),
        "google": ("GOOGLE_API_KEY", settings.google_api_key),
    }
    default_name, default_value = provider_keys[settings.llm_default_provider]
    if _looks_like_placeholder(default_value):
        missing.append(default_name)

    if missing:
        # Names only — never the values.
        raise SystemExit(
            "FATAL: dm-tool-worker is missing required production configuration: "
            + ", ".join(missing)
            + ". Refusing to start — background jobs would fail at runtime. Set "
            "these on the worker service. (Variable names only; no values logged.)"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
