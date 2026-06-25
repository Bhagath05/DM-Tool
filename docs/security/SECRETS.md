# DM Tool — Secret Management & Rotation Runbook

> Source of truth: this file. If a secret isn't listed here, it shouldn't exist.
> Last verified: 2026-06-10 (Phase S1.1).

---

## 1. Repository hygiene state

- `.env` and `.env.local` are gitignored at the repo root (see `.gitignore`).
- `.env.example` is the only env template that is committed. It contains
  placeholder values only — every secret line ends in `replace_me`,
  `your-instance`, or empty.
- The repository at `/Users/bhagath/DM_Tool/ai-cmo` is **not currently a
  git repository**. When `git init` is run, the `.gitignore` patterns
  already in place will prevent the local `.env` from being tracked, and
  `.pre-commit-config.yaml` + `.gitleaks.toml` (Phase S1.2) will block
  future accidental commits.

## 2. Secret inventory

Each row is a secret name, its purpose, scope, owner, rotation cadence,
and the storage tier it should live in once the project moves out of
local-`.env` development.

| Secret | Purpose | Scope | Required by | Cadence | Storage tier |
|---|---|---|---|---|---|
| `CLERK_SECRET_KEY` | Clerk server-side API key | apps/web, apps/api | clerk + hybrid AUTH_MODE | 90d | Vault / SOPS |
| `CLERK_JWT_ISSUER` | Issuer URL for JWT verification | apps/api | clerk + hybrid AUTH_MODE | on Clerk rotation | Vault |
| `CLERK_JWKS_URL` | JWKS endpoint for public keys | apps/api | clerk + hybrid AUTH_MODE | on Clerk rotation | Vault |
| `CLERK_JWT_AUDIENCE` | Required JWT audience claim | apps/api | **production** | 90d | Vault |
| `CLERK_WEBHOOK_SIGNING_SECRET` | Svix HMAC for webhook verify | apps/api | webhook receiver | 90d | Vault |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Public Clerk SDK key | apps/web (bundled) | clerk + hybrid AUTH_MODE | 90d | Build env |
| `ANTHROPIC_API_KEY` | Claude API access | apps/api | LLM_DEFAULT_PROVIDER=anthropic | 90d | Vault / SOPS |
| `OPENAI_API_KEY` | OpenAI API access | apps/api | image render + fallback LLM | 90d | Vault / SOPS |
| `GOOGLE_API_KEY` | Gemini API access | apps/api | LLM_DEFAULT_PROVIDER=google | 90d | Vault / SOPS |
| `IP_HASH_PEPPER` | SHA-256 pepper for lead-IP hashing | apps/api | **production** (GDPR) | yearly | Vault |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile public | apps/web | lead capture in prod | on CF rotation | Build env |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile server | apps/api | lead capture in prod | on CF rotation | Vault |
| `MEDIA_SIGNING_SECRET` | HMAC for signed media URLs | apps/api | **production** | 90d | Vault |
| `INTEGRATION_TOKEN_KEY` | Fernet key for OAuth token encryption at rest | apps/api | any connected integration | yearly + on incident | Vault |
| `IG_CLIENT_ID` / `IG_CLIENT_SECRET` | Instagram OAuth | apps/api | Instagram connector | on Meta rotation | Vault |
| `STRIPE_SECRET_KEY` | Stripe server API key | apps/api | **billing live** | 90d | Vault |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature secret | apps/api | **billing live** | on endpoint rotation | Vault |
| `GOOGLE_APPLICATION_CREDENTIALS` | Vertex AI service-account (Veo 3) | apps/api worker | **video + provider=veo3** | 90d | Vault / workload identity |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS | apps/api worker | **video + tts=elevenlabs** | 90d | Vault |
| `S3_*` (bucket/region/endpoint + IAM creds) | Creative object storage | apps/api worker | **video + backend=s3** | per IAM rotation | Vault / IAM role |
| `SENTRY_DSN` / `NEXT_PUBLIC_SENTRY_DSN` | Sentry project DSN | both | **production** | rare | Build env |
| `SENTRY_AUTH_TOKEN` | Source-map upload at build time | apps/web build | CI/build only | 90d | CI secret |
| `DATABASE_URL` | Postgres DSN | apps/api | always | on rotation | Vault |
| `REDIS_URL` | Redis DSN | apps/api | always | on rotation | Vault |

**Format note:** every secret value MUST be set via environment variable.
No secret is allowed in code, in a checked-in config file, in a JSON
fixture, in a log, in a Sentry event, or in an audit row.

## 3. Rotation procedures (per provider)

> Order: rotate at the provider → roll the deploy → invalidate the old
> value at the provider → confirm no traffic on the old key.

### Clerk (`CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_SECRET`)

1. Sign in to https://dashboard.clerk.com → API Keys.
2. Click **Generate new key**. Copy the new value.
3. In your deploy environment, update `CLERK_SECRET_KEY` (and the
   matching `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` if you also rotated the
   publishable key).
4. Trigger a deploy. Wait for the rollout to complete.
5. Back in the Clerk dashboard, revoke the old key.
6. Confirm `/api/v1/users/me` and a sign-in flow both still work.
7. For webhooks: regenerate the Svix signing secret under
   Webhooks → your endpoint → Signing Secret → Rotate. Update
   `CLERK_WEBHOOK_SIGNING_SECRET`. Trigger a test event and confirm the
   `apps/api/aicmo/modules/security/router.py` webhook receiver still
   returns 200.

### Clerk JWT audience / issuer

`CLERK_JWT_ISSUER` and `CLERK_JWKS_URL` only change when Clerk rotates
their signing keys (rare) or you migrate Clerk instances. `CLERK_JWT_AUDIENCE`
is set once per environment and is required by
`validate_production_secrets()`. When changing it:

1. Set the new value in the deploy environment.
2. Restart the API. Sessions remain valid as long as the issuer + JWKS
   stay the same — only `aud` is re-checked.

### Anthropic / OpenAI / Google

All three providers expose key revocation in their dashboards:

- Anthropic: https://console.anthropic.com → Settings → API Keys.
- OpenAI: https://platform.openai.com → API keys.
- Google AI Studio: https://aistudio.google.com → API keys.

Procedure:

1. Mint a new key alongside the existing one.
2. Update the deploy env var.
3. Trigger a generate-content request; confirm via `llm_traces` table
   that the call succeeded.
4. Revoke the old key in the provider dashboard.

### `IP_HASH_PEPPER` (GDPR-sensitive)

Rotating the pepper invalidates lookups against prior-period hashes —
that's intentional, since they're meant to be one-way. Only rotate if
you suspect the pepper has leaked. Procedure:

1. Generate a new pepper: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Set `IP_HASH_PEPPER` in the deploy env.
3. Restart the API.
4. Existing hashes in `lead_captures.ip_hash` remain valid for storage
   but cannot be correlated with new captures — accept that one-time
   loss of joinability.

### `INTEGRATION_TOKEN_KEY` (Fernet — encrypted OAuth tokens at rest)

The Fernet key encrypts user OAuth tokens in `integration_credentials`.
Rotating it requires re-encrypting every stored token.

1. Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. **Two-key window** (planned, not yet implemented — flag for Phase S3):
   add a `INTEGRATION_TOKEN_KEY_OLD` env var so `crypto.py` can decrypt
   with either, then re-encrypt with the new key in a backfill job.
3. Until the two-key window exists, rotation requires:
   a. Pause all integrations (set every `integration.status = 'paused'`).
   b. Require users to reconnect (clears the stored token).
   c. Swap the key + restart.

`rotated_at` already exists on the `integration_credentials` row — wire
the backfill to populate it once the two-key window lands.

### `MEDIA_SIGNING_SECRET`

Signed media URLs become invalid the moment the key rotates. Procedure:

1. Set the new value in the deploy env.
2. Restart the API.
3. Any cached signed URL the frontend is sitting on returns 403 — the
   frontend re-fetches via the `signed_url` endpoint. Acceptable for a
   key rotation; do not rotate during a campaign launch.

### Stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)

Required only when `BILLING_LIVE_ENABLED=true` (the production boot guard
enforces this). No card data ever touches our DB — Checkout + Billing
Portal are Stripe-hosted (PCI SAQ-A).

1. Stripe Dashboard → Developers → API keys → roll the secret key.
2. Update `STRIPE_SECRET_KEY` in the deploy env; redeploy.
3. Revoke the old key in the dashboard.
4. Webhook secret: Developers → Webhooks → your endpoint
   (`/api/v1/billing/webhooks/stripe`) → roll the signing secret →
   update `STRIPE_WEBHOOK_SECRET` → send a test event and confirm the
   receiver returns 200 with `{"status":"processed"}`.

### `DATABASE_URL` / `REDIS_URL`

Rotated when the underlying DB credentials change. Procedure:

1. Mint a new DB user with the same role grants OR rotate the password
   on the existing user.
2. Update `DATABASE_URL`.
3. Rolling restart of the API. SQLAlchemy's pool reconnects.
4. Revoke the old DB password.

## 4. Boot guards

Two startup gates enforce the secret posture (see `apps/api/aicmo/main.py`):

1. `assert_auth_config_valid()` — refuses to start if `AUTH_MODE` is
   `clerk` or `hybrid` but Clerk env vars are missing / placeholders.
2. `validate_production_secrets()` — when `API_ENV=production`:
   - `AUTH_MODE` must be `clerk` (never `demo` or `hybrid`).
   - `CLERK_SECRET_KEY`, `CLERK_JWT_ISSUER`, `CLERK_JWKS_URL`,
     `CLERK_JWT_AUDIENCE`, `IP_HASH_PEPPER`, `MEDIA_SIGNING_SECRET`,
     `SENTRY_DSN` must all be set to non-placeholder values.
   - The configured `LLM_DEFAULT_PROVIDER`'s API key must be set.
   - Other LLM keys may be empty if the provider isn't in use.

These gates are deliberately blunt: a misconfigured prod deploy never
binds the port. There is no "warn" mode.

## 5. What is NOT a secret

These appear in env files but are PUBLIC by design and may be checked in:

- `NEXT_PUBLIC_*` values (baked into the client bundle at build time).
- `API_ENV`, `API_LOG_LEVEL`, `API_VERSION`.
- `NEXT_PUBLIC_API_URL` (the API origin is public knowledge).
- `LLM_DEFAULT_PROVIDER`, `LLM_DEFAULT_MODEL`.
- `MEDIA_DIR`, `IMAGE_RENDER_DAILY_CAP`, `LEAD_CAPTURE_RATE_LIMIT`.

## 6. Where a leak would be caught (defence in depth)

| Layer | Mechanism | Status |
|---|---|---|
| Source control | `.gitignore` excludes `.env*`; `.env.example` is whitelisted | ✅ in place |
| Pre-commit | `gitleaks` via `.pre-commit-config.yaml` | 📦 prepared (S1.2 — activates on `git init`) |
| CI | `.github/workflows/security.yml` runs gitleaks + secret scanners | 📦 prepared (activates on push to GitHub) |
| Runtime | `validate_production_secrets()` boot gate | ✅ in place |
| Telemetry | Sentry scrubber strips Authorization / cookies / known secret patterns | 🚧 S2.8 |
| Audit | `audit_events.metadata_json` schema-validated — no raw token storage | ✅ in place |
| Logging | structlog config does not log Authorization header; rate-limit hashes IPs | ✅ in place |

## 7. Incident response

If a secret is suspected to be exposed (committed to a public repo,
posted in a screenshot, leaked via a customer report):

1. Rotate the key per Section 3 within 15 minutes.
2. Open an incident ticket.
3. Review `audit_events` and provider dashboards for unauthorized use
   during the exposure window.
4. If `INTEGRATION_TOKEN_KEY` was exposed: assume all stored OAuth
   tokens are compromised — force-disconnect every integration and
   notify affected users.
5. Patch the leak vector (e.g. add the offending file pattern to
   `.gitleaks.toml`).
