# Environment Variables — Reference

Source of truth for every variable the app reads. The canonical template is
[`.env.example`](../../.env.example); this doc adds *where each var is set* and
*when it's required*. The backend boot guard (`validate_production_secrets`,
`aicmo/config.py`) refuses to start in production if a required secret is
missing or still holds a placeholder (`replace_me` / `your-instance`).

**Where things are set in production**
- **Render** (backend `dm-tool-api` + worker `dm-tool-worker`): all non-`NEXT_PUBLIC_*` vars.
- **Vercel** (frontend `apps/web`): the `NEXT_PUBLIC_*` vars only.
- `DATABASE_URL` / `REDIS_URL` are injected by Render from the managed
  Postgres/Redis services (see `render.yaml`).

Legend: **R** = required in production · **P** = required only when its feature is enabled · **O** = optional.

## Core

| Variable | Where | Req | Notes |
|---|---|---|---|
| `API_ENV` | Render | R | `development` \| `staging` \| `production`. Gates prod boot checks + the storage safety gate. |
| `API_LOG_LEVEL` | Render | O | `INFO` default. |
| `API_VERSION` | Render | O | Release tag (Sentry/source-map correlation). |
| `API_CORS_ORIGINS` | Render | R | Comma-separated allowlist. Must include the Vercel origin. **No wildcard.** |
| `DATABASE_URL` | Render (injected) | R | Normalized to `postgresql+psycopg://` automatically. |
| `REDIS_URL` | Render (injected) | R (worker) | Arq broker. Web degrades gracefully if down; worker requires it. |

## Auth (Clerk)

| Variable | Where | Req | Notes |
|---|---|---|---|
| `AUTH_MODE` | Render | R | **Must be `clerk` in production** (boot guard enforces). `hybrid`/`demo` are dev/staging. |
| `NEXT_PUBLIC_AUTH_MODE` | Vercel | R | Must match `AUTH_MODE`. |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Vercel | R | `pk_live_…` in prod. |
| `CLERK_SECRET_KEY` | Render | R | `sk_live_…`. |
| `CLERK_JWT_ISSUER` | Render | R | Exactly the Clerk Frontend API URL, e.g. `https://<slug>.clerk.accounts.dev` (no trailing slash). |
| `CLERK_JWKS_URL` | Render | R | `<issuer>/.well-known/jwks.json`. |
| `CLERK_JWT_AUDIENCE` | Render | O | Set only if your Clerk tokens carry an `aud`. Leaving empty keeps aud-verification off (default Clerk session tokens have no `aud`). |
| `CLERK_WEBHOOK_SIGNING_SECRET` | Render | O | `whsec_…`. Empty → webhook route returns 503. |

## LLM / AI providers

| Variable | Where | Req | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Render | R | Default provider (Claude). Without it, AI features fall back to deterministic output. |
| `OPENAI_API_KEY` | Render | P | Image generation + OpenAI TTS. Without it, image render errors/stubs. |
| `GOOGLE_API_KEY` | Render | O | Alternate LLM provider. |
| `LLM_DEFAULT_PROVIDER` | Render | O | `anthropic` default. |
| `LLM_DEFAULT_MODEL` | Render | O | `claude-sonnet-4-6` default. |

## Security / lead capture

| Variable | Where | Req | Notes |
|---|---|---|---|
| `IP_HASH_PEPPER` | Render | R | SHA-256 pepper — raw IPs are never stored (GDPR). |
| `MEDIA_SIGNING_SECRET` | Render | R | HMAC key for signed media URLs (no auth fallback in prod). |
| `INTEGRATION_TOKEN_KEY` | Render | P | Fernet key (44-char base64). Required before connecting any OAuth provider; encrypts stored tokens at rest. |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Vercel / Render | O | Cloudflare Turnstile for lead capture. Empty = bypass (dev). |
| `LEAD_CAPTURE_RATE_LIMIT` | Render | O | Per-IP/min on public capture. |
| `PUBLIC_BASE_URL` | Render | R | Public origin used to build invite/OAuth/media URLs. Set to the Vercel URL. |

## Media / storage

| Variable | Where | Req | Notes |
|---|---|---|---|
| `MEDIA_BACKEND` | Render | R | `local` \| `s3` \| `r2`. **`local` in production disables image generation + exports** (safety gate). See [object-storage.md](object-storage.md). |
| `MEDIA_DIR` | Render | O | Local disk path (dev/staging only). |
| `S3_BUCKET` / `S3_REGION` / `S3_ENDPOINT_URL` | Render | P | Required when `MEDIA_BACKEND` is `s3`/`r2`. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Render | P | boto3 credentials for S3/R2. |
| `IMAGE_RENDER_DAILY_CAP` | Render | O | Per-user/day cost control. |

## Feature flags (all default OFF — features ship dark)

| Variable | Where | Default | Notes |
|---|---|---|---|
| `STUDIO_ENABLED` / `NEXT_PUBLIC_STUDIO_ENABLED` | Render / Vercel | false | Creative Studio. Requires object storage before enabling. |
| `POSTER_ENABLED` | Render | false | LinkedIn poster studio (generates images → needs object storage). |
| `VIDEO_ENABLED` | Render | false | Video pipeline. |
| `BILLING_LIVE_ENABLED` | Render | false | true → Stripe checkout/portal live. |
| `BILLING_ENFORCE_LIMITS` | Render | false | true → quota gate blocks over-limit (record-only when false). |

## Billing (Stripe) — required only when `BILLING_LIVE_ENABLED=true`

| Variable | Where | Notes |
|---|---|---|
| `STRIPE_SECRET_KEY` | Render | `sk_live_…`. |
| `STRIPE_WEBHOOK_SECRET` | Render | `whsec_…` from the Stripe webhook endpoint. |

Plan prices + quotas live in the DB (`plan` / `plan_quota` tables), not env.

## Video / TTS — required only when `VIDEO_ENABLED=true` + provider selected

`VIDEO_DEFAULT_PROVIDER`, `TTS_DEFAULT_PROVIDER`, `VIDEO_RENDER_DAILY_CAP`,
`VIDEO_ORG_MONTHLY_BUDGET_CENTS`, `VERTEX_PROJECT`, `VERTEX_LOCATION`,
`GOOGLE_APPLICATION_CREDENTIALS`, `ELEVENLABS_API_KEY`.

## Frontend

| Variable | Where | Req | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Vercel | R | The Render backend origin. |

## Observability (Sentry)

| Variable | Where | Req | Notes |
|---|---|---|---|
| `SENTRY_DSN` | Render | R | Empty → no Sentry init (error reporting off). |
| `NEXT_PUBLIC_SENTRY_DSN` | Vercel | R | Frontend error reporting. |
| `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | Render / Vercel | O | Defaults to `API_ENV`. |
| `SENTRY_TRACES_SAMPLE_RATE` / `SENTRY_PROFILES_SAMPLE_RATE` | Render | O | `0.0` default. |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | build | O | Source-map upload at build time. |

## Unused-variable policy

There are **no orphan env vars** — every entry above maps to a field in
`aicmo/config.py:Settings` (backend) or a `NEXT_PUBLIC_*` read in the web app.
If you add a var, add it to `.env.example` and this table, or the config
layer will ignore it silently.
