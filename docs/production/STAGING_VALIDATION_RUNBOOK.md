# Staging validation runbook (Phase 8)

Executable procedures to move DM Tool from **CODE VERIFIED** → **STAGING
VERIFIED** → **LIVE VERIFIED**. **None of these were run in the Phase-8 working
environment** (no live Postgres/Redis/Render/AWS/Clerk/provider-OAuth reachable
there), so every box below is **unchecked** and must be executed by a human
operator on real staging. Do **not** deploy production, apply production
migrations, create production credentials, or change DNS/Clerk-prod from here.

Status labels: **CODE VERIFIED** = code + tests + build pass (done). **STAGING
VERIFIED** = the boxes here pass on real staging. **LIVE VERIFIED** = provider
E2E on real accounts passes. **PRODUCTION READY** = all of the above + sign-off.

---

## 0. Prerequisites (staging, not production)
- [ ] Render **staging** services: API + worker (`API_ENV=staging`), managed
      Postgres, managed Redis.
- [ ] Clerk **staging** instance (separate keys); `AUTH_MODE=clerk` on staging
      to exercise real auth (or `hybrid` if a demo path is needed).
- [ ] `INTEGRATION_TOKEN_KEY`, `MEDIA_SIGNING_SECRET`, `IP_HASH_PEPPER`,
      `SENTRY_DSN` (staging project), default-LLM key — set on API **and** worker.
- [ ] AWS **staging** bucket + IAM role via Render OIDC (see
      `docs/security/AWS_S3_HARDENING.md`); `MEDIA_BACKEND=s3`, `S3_BUCKET`,
      `S3_REGION`; **no static AWS keys**.
- [ ] Provider **test** OAuth apps (FB/YouTube/LinkedIn/Pinterest) — never reuse
      production OAuth secrets.

## 1. Migration 0070 (staging first, with rollback)
`0070_social_asset_provider` is written but **not applied**. Chain +
model verified (sole child of `0069`; `connection_id` nullable + `provider_slug`
+ `integration_connection_id` FK + index; existing rows stay valid).
- [ ] **Backup**: managed-Postgres snapshot of staging DB.
- [ ] Apply: `alembic upgrade head` (runs automatically in `start.sh` on deploy).
- [ ] Schema check: `\d social_assets` shows `connection_id` **nullable**, new
      `provider_slug` + `integration_connection_id` columns, the FK, and
      `ix_social_assets_provider_slug`.
- [ ] Existing-row check: pre-existing Instagram rows keep `connection_id`; new
      columns NULL. `SELECT count(*)` unchanged.
- [ ] App boots (no `SystemExit`); `/health` green; worker boots.
- [ ] **Rollback procedure (if needed):** `alembic downgrade 0069_website_discovery`
      (drops the 3 additions, restores NOT NULL — safe only before any
      provider-collected NULL-connection rows exist), then restore snapshot if
      data changed.

## 2. AWS S3 security baseline (verify on the staging bucket)
- [ ] Block Public Access = ON (all four) at bucket + account.
- [ ] Object Ownership = Bucket owner enforced; ACLs disabled.
- [ ] Default encryption = ON (SSE-S3/AES256).
- [ ] TLS-only bucket policy attached (deny `aws:SecureTransport=false`).
- [ ] No website hosting; no anonymous access; no wildcard-public principal.
- [ ] App role = 4-action least-privilege only; assumed via Render OIDC (STS
      short-lived creds); **no static keys on the services**.

## 3. Video E2E (Veo seam — smallest safe throwaway asset)
Set `studio_enabled=true` + `video_enabled=true` on **staging only**; use a
throwaway prompt (no customer media).
- [ ] Submit a video job → accepted, async (worker), API returns immediately.
- [ ] Provider output received; **MIME + MP4 `ftyp` validation passes**
      (`storage/validation.py`).
- [ ] Inject a deliberately-malformed provider payload → routed through
      `failed_rendering`; **nothing persisted** (validated by
      `tests/creative/test_media_security.py`; confirm live behavior too).
- [ ] `CreativeAsset` row persisted (storage_key, mime, duration, status=ready);
      `video_render` + cost ledger + AI-audit written.
- [ ] S3 object is **private** (direct URL → 403); presigned URL plays;
      **presigned URL expires** within ≤1h; a second request after expiry → 403.
- [ ] No tokens/secrets/URLs in logs (grep worker logs for the token/bucket).
- [ ] Tenant isolation: a second tenant cannot fetch tenant A's asset URL.
- [ ] Failed-render temp state cleaned; lifecycle rule expires `tmp/`.
Then set `video_enabled=false` again after the test.

## 4. Provider OAuth E2E (one controlled test account each)
For **Facebook Pages, YouTube, LinkedIn, Pinterest**:
- [ ] OAuth connect → `IntegrationConnection` state = ACTIVE.
- [ ] `ensure_access_token` resolves (decrypt/refresh) — **no token in logs**.
- [ ] Provider API read succeeds; account metadata populated.
- [ ] `collect_metrics_cron` writes `ConnectorMetric`;
      `collect_content_metrics_cron` writes `SocialAsset` + `PerformanceSignal`
      for a published test post (respect per-platform metric availability;
      unavailable metrics stay absent, never fabricated).

## 5. Full loop E2E (CONNECT → … → ATTRIBUTE)
- [ ] CONNECT (above) → COLLECT (metrics land) → ANALYZE (analytics show real
      data) → RECOMMEND (advisor uses computed evidence) → GENERATE (Create
      Similar → Creative Studio pre-filled draft) → **HUMAN APPROVAL**.
- [ ] **Approval-gate proof:** attempt publish while `approval_status=pending`
      → **rejected**; while `rejected` → **rejected**; only after explicit
      **approve** does publish proceed (`PUBLISHABLE_APPROVALS`).
- [ ] PUBLISH → `platform_post_id` recorded → post-publish `PerformanceSignal`
      collected → `recommendation_id` preserved end-to-end → recommendation
      effectiveness computed (honest, **non-causal** language).
- [ ] Tenant isolation holds at every step (A cannot see B's data).

## 6. Observability
- [ ] Sentry (staging) receives errors; secrets/tokens/URLs scrubbed.
- [ ] Worker + video + S3 failures are visible with provider slug + safe error
      category; raw provider responses are not logged.

## 7. Sign-off
- [ ] All boxes above checked on staging → mark **STAGING VERIFIED**.
- [ ] Provider E2E on real accounts → mark **LIVE VERIFIED**.
- [ ] Then, and only then, plan the production cutover (separate approval).
