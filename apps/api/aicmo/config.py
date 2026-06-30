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

    # AUTH_MODE — single source of truth for which auth backend is in
    # effect:
    #   "demo"   → no Clerk verification ever. Every request resolves to
    #              a stable dev user. Public-demo product flow.
    #   "clerk"  → strict Clerk auth. Missing/invalid JWT → 401. Refuses
    #              to boot without Clerk env vars.
    #   "hybrid" → both. No Authorization header → demo user (landing →
    #              Open Dashboard works anonymously). Bearer token →
    #              verified as a Clerk JWT (real signed-in user). Lets
    #              the demo journey AND real sign-in coexist. Like
    #              "clerk", refuses to boot without Clerk env vars.
    auth_mode: Literal["demo", "clerk", "hybrid"] = "demo"

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

    clerk_jwt_issuer: str = Field(default="")
    clerk_jwks_url: str = Field(default="")
    clerk_secret_key: str = Field(default="")
    # When set, JWT verification enforces `aud` matches this value.
    # Required in production by validate_production_secrets().
    clerk_jwt_audience: str = Field(default="")

    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")

    llm_default_provider: Literal["anthropic", "openai", "google"] = "openai"
    llm_default_model: str = "gpt-4o-mini"

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
        description="HMAC key for signed media URLs. Falls back to clerk_secret_key if empty.",
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

    # -----------------------------------------------------------------
    # Phase 10.2c — Clerk webhook signature verification.
    #
    # Clerk signs webhook payloads with Svix (HMAC-SHA256 over
    # `${msg_id}.${timestamp}.${body}` using a base64-decoded shared
    # secret). The secret has format `whsec_<base64>`.
    #
    # Empty in dev = webhook receiver returns 503. We never accept
    # unverified webhook payloads — better to drop events than to
    # ingest forged ones.
    # -----------------------------------------------------------------
    clerk_webhook_signing_secret: str = Field(
        default="",
        description=(
            "Svix signing secret from the Clerk dashboard. Empty disables "
            "the webhook endpoint (503). Format: 'whsec_<base64>'."
        ),
    )
    clerk_webhook_tolerance_seconds: int = Field(
        default=300,
        description="Reject webhook payloads older than this (replay defence).",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

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


def validate_production_secrets(settings: "Settings") -> None:
    """Refuse to boot in production with placeholder / missing secrets.

    Runs from main.py at module load, after assert_auth_config_valid().
    No-op outside production — dev + staging stay unchanged so the demo
    flow keeps working with `replace_me` placeholders.
    """
    if settings.api_env != "production":
        return

    errors: list[str] = []

    # Auth posture: prod must enforce real Clerk verification.
    if settings.auth_mode != "clerk":
        errors.append(
            f"AUTH_MODE must be 'clerk' in production (got {settings.auth_mode!r}). "
            "demo/hybrid expose unsigned access paths."
        )

    # Required secret bundles in prod. Each tuple is (env_name, value).
    required = [
        ("CLERK_SECRET_KEY", settings.clerk_secret_key),
        ("CLERK_JWT_ISSUER", settings.clerk_jwt_issuer),
        ("CLERK_JWKS_URL", settings.clerk_jwks_url),
        ("CLERK_JWT_AUDIENCE", settings.clerk_jwt_audience),
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
