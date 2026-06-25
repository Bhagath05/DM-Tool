# Video Generation — V0 (Foundation) Technical Design

> The dark-launch skeleton for Veo 3 video. Design only — no implementation.
> Parent: `VIDEO_GENERATION_ARCHITECTURE.md`. Builds on Phase 0 (jobs) +
> Phase 1 (metering), both shipped. Date: 2026-06-11.

**Locked architecture decisions (this design honors all five):**
1. Audio — **always layer TTS** over Veo audio; brand-voice consistency is the priority; provider-abstracted.
2. TTS — **ElevenLabs** primary, pluggable behind a `TTSProvider` ABC.
3. Metering — **both** per-video quota AND per-second cost; track provider cost, storage cost, render duration, usage events.
4. Storage — **S3-compatible object storage**; no video bytes in Postgres; PG is the source of truth for metadata/audit/quota/cost/status/signed-URL refs.
5. Veo — **Vertex AI service-account**; Veo is the first `VideoProvider` impl; no vendor lock-in.

**V0 goal:** every abstraction, table, config, policy, and job *exists and
is tested*, but **no real provider is called** — `VIDEO_ENABLED=false` by
default means zero behavior change. V1 fills the stubs with Veo/ElevenLabs/S3.

> ✅ **CREATIVE CORE NAMING (approved 2026-06-11).** Video V0 ships as the
> **first subsystem of a unified Creative Platform core**, per
> `CREATIVE_PLATFORM_ARCHITECTURE_REVIEW.md`. Shared core tables are
> media-agnostic: `creative_project / creative_asset / creative_variant /
> creative_cost_event / creative_format` (+ `brand_kit`, `creative_template`,
> `creative_export`). Only `video_scene` + `video_render` stay
> video-specific. Existing `visuals`/`content` are **not** rewritten — they
> register into `creative_asset` later, additively. This section reflects
> that naming.

---

## 1. Technical design

### 1.1 Two modules — Creative **core** + Video **subsystem**
The core is media-agnostic and is shared by every future creative type
(posters/banners/carousels/…). The video subsystem holds only
video-specific tables + the Veo/TTS abstractions.
```
modules/creative/                 # CORE (media-agnostic)
  __init__.py
  models.py            # creative_project, creative_asset, creative_variant,
                       #   creative_cost_event, creative_format, brand_kit,
                       #   creative_template, creative_export   (all TenantMixin)
  schemas.py           # CreativeType, MediaType, CreativeStatus + request/response
  service.py           # project CRUD + state-machine transitions (no provider calls)
  cost.py              # creative_cost_event writer + per-org budget read
  metering.py          # usage-kind emit (reuses billing.record_metered)
  formats.py           # DB-backed creative_format catalog reader
  router.py            # /api/v1/creative/* endpoints (flag-gated) — §3
  storage/
    base.py            # StorageBackend protocol (put/signed_url/delete) + StorageRef
    local.py           # LocalDiskBackend (dev/test — reuses media_dir + media_url HMAC)
    s3.py              # S3Backend (prod — presigned URLs)  [interface V0, impl V1]
    registry.py        # select by media_backend config

modules/video/                    # SUBSYSTEM (video-specific)
  __init__.py
  models.py            # video_scene, video_render  (FK → creative_project/asset)
  service.py           # scene/render helpers (no provider calls in V0)
  tasks.py             # Arq stub pipeline (@tenant_job, registered in ALL_JOBS)
  providers/
    base.py            # VideoProvider ABC
    stub.py            # StubVideoProvider (deterministic, no network)
    registry.py        # select by video_default_provider  (veo3 added in V1)
  tts/
    base.py            # TTSProvider ABC
    stub.py            # StubTTSProvider
```
Nothing under (future) `video/providers/veo3.py`, `video/tts/elevenlabs.py`,
`creative/storage/s3.py` makes a real call in V0 — they are interface +
(for stub/local) working no-network impls.

### 1.2 The three abstractions (no vendor lock-in)

**`VideoProvider` (ABC)** — Veo is V1's first impl; stub backs V0/tests:
```
submit(prompt, *, aspect, resolution, duration_s, seed_image=None,
       negative_prompt=None) -> ProviderOperation          # async submit
poll(operation) -> ProviderStatus   # pending | done(remote_uri) | failed | blocked
fetch(remote_uri) -> bytes                                  # → handed to StorageBackend
estimate_cost(duration_s, resolution) -> Cents
name -> str                                                 # 'stub' | 'veo3'
```
*Decision 5:* `veo3.py` (V1) authenticates via a **Vertex AI service
account** (workload identity / SA JSON in secrets) and rides Veo's
long-running operation through `poll`. The ABC hides all of that.

**`TTSProvider` (ABC)** — *Decision 1+2:* audio is **always** our TTS
layer (Veo's native audio is muted in assembly); ElevenLabs is V1's first
impl, stub backs V0:
```
synthesize(text, *, voice_id, format='mp3') -> bytes
estimate_cost(char_count) -> Cents
name -> str                                                 # 'stub' | 'elevenlabs'
```

**`StorageBackend` (protocol)** — *Decision 4:* no bytes in PG; S3 is the
prod target; local disk for dev/tests:
```
put(tenant_key, data, content_type) -> StorageRef           # backend + object key
signed_url(ref, expires_s) -> str
delete(ref) -> None
```
`StorageRef = {backend: 'local'|'s3', key: str}` is what Postgres stores —
never bytes. `LocalDiskBackend` reuses the existing `media_dir` +
`media_url` HMAC signing; `S3Backend` (V1) uses presigned URLs. The
existing `MEDIA_BACKEND` swap point already anticipated this.

### 1.3 Config flags (all default to the safe/off value)
```
video_enabled: bool = False                 # master kill switch — V0 ships dark
video_default_provider: Literal["stub","veo3"] = "stub"
tts_default_provider:   Literal["stub","elevenlabs"] = "stub"
media_backend:          Literal["local","s3"] = "local"

# cost + abuse caps (Decision 3 + security)
video_render_daily_cap: int = 5             # per user/day (video is expensive)
video_org_monthly_budget_cents: int = 0     # 0 = use plan default; per-org override in DB

# secrets — required ONLY when video_enabled (boot-guarded) — §4
vertex_project: str = ""
vertex_location: str = "us-central1"
google_application_credentials: str = ""    # SA JSON path / workload identity
elevenlabs_api_key: str = ""
s3_bucket: str = ""
s3_region: str = ""
s3_endpoint_url: str = ""                    # S3-compatible (R2/MinIO/AWS)
```

### 1.4 State machine + jobs (async-only, tenant-scoped)
`video_project.status` drives the pipeline (architecture §3.8). V0 ships
the **job skeletons** decorated with Phase-0 `@tenant_job` and registered
in `ALL_JOBS`, but their bodies are stubs that transition state using the
`StubVideoProvider`/`StubTTSProvider` — **no network, no spend**. This
proves the whole async pipeline + tenant isolation end-to-end before any
real provider exists. Real bodies land in V1+.

Every long-running step stays async through Arq (no blocking the API) —
honored from V0 via the stub jobs that already use the submit→poll shape.

### 1.5 What V0 explicitly does NOT do
- No real Veo / ElevenLabs / Vertex / S3 calls (V1).
- No ffmpeg assembly / voiceover / subtitles / brand-kit passes (V2–V4).
- No variants / A/B / publish (V5–V6).
- No frontend (a later UI pass).

---

## 2. Database impact

**One additive, reversible migration `0034_video_foundation`.** Creates the
schema, the format catalog, RLS policies, the metering kinds, and the RBAC
seed. No existing table is altered except the two extensions noted.

### 2.1 New tables (all `TenantMixin` + `TimestampMixin`, UUID PKs)
**Creative core (media-agnostic):** `creative_project` (+ `creative_type`
+ `media_type` discriminators), `creative_asset` (the unified Asset
Library row — `media_type`, `creative_type`, `source_kind` + `source_id`
polymorphic pointer, `published_ref`, `storage_ref`), `creative_variant`,
`creative_cost_event` (+ `media_type`), `creative_format` (DB catalog),
`brand_kit`, `creative_template`, `creative_export`.
**Video subsystem:** `video_scene`, `video_render` (FK →
`creative_project` / `creative_asset`).
Renders/assets store `storage_ref` (`{backend, key}`) **instead of a raw
file_path** — no bytes, backend-agnostic.

`video_cost_event` (Decision 3) records **provider cost, storage cost, and
render duration** per stage: `stage`, `provider`, `units`,
`unit_cost_cents`, `cost_cents`, `duration_ms` (for render seconds),
`occurred_at`.

### 2.2 Seed: `video_format` catalog (DB-configurable, tunable without deploy)
7 rows — instagram_reels, tiktok, youtube_shorts, meta_ads, facebook_ads,
ugc_ad, product_commercial — each with aspect/resolution/max_duration/
seeding/style (architecture §9).

### 2.3 Indexes
`video_project (brand_id, created_at DESC)`,
`video_scene (video_project_id, scene_index)`,
`video_render (provider_operation_id)` (poll lookup),
`video_render (video_project_id)`,
`video_cost_event (organization_id, occurred_at)`.

### 2.4 RLS readiness (preserved)
All new tenant tables are added to `db/rls.RLS_TABLES` and get a dormant
`rls_tenant_isolation_*` policy in the same migration — org-scoped, not
enabled (consistent with `RLS_ACTIVATION.md`). Video inherits the exact
DB-isolation posture as leads/campaigns/content.

### 2.5 Metering extensions (Decision 3 — both units)
- Extend `usage_event.kind` CHECK with **`video_generation`** (per-video
  quota) and **`video_second`** (per-second usage). CHECK goes 8 → 10 kinds.
- Seed `plan_quota` rows for `video_generation` per plan (DB-configurable;
  placeholders, e.g. free=2, starter=30, growth=300, scale/early_access=∞).
  `video_second` is tracked but typically left unbounded (fair-use).

### 2.6 RBAC seed
Insert permissions `video.create`, `video.read`, `video.publish`; grant
read+create to owner/admin/editor, read to analyst, publish to owner/admin
(mirrors the `content.*` grants). Same pattern as migration 0014.

### 2.7 Reversibility
`downgrade()` drops the 8 tables, removes the RLS policies, reverts the
`usage_event` CHECK to its 0033 (8-kind) form, and deletes the seeded
permissions/quotas. Verified live (apply → downgrade → re-apply) before
sign-off, same as 0031/0032/0033.

---

## 3. APIs affected

New router `/api/v1/video/*`, **flag-gated** — when `video_enabled=false`
(default) every endpoint returns `409` with "video generation isn't
enabled yet", so V0 is inert in the running product (mirrors billing's
dark launch). Surface registered in V0 so the contract is pinned by tests:

| Method | Path | Permission | V0 behavior |
|---|---|---|---|
| POST | `/video/projects` | `video.create` | create draft + pre-flight cost estimate (stub estimate) |
| GET | `/video/projects` | `video.read` | list (brand-scoped) |
| GET | `/video/projects/{id}` | `video.read` | status + scenes + assets + cost |
| POST | `/video/projects/{id}/start` | `video.create` | enqueue the (stub) pipeline |
| POST | `/video/projects/{id}/cancel` | `video.create` | cancel |
| GET | `/video/projects/{id}/cost` | `video.read` | ledger rollup |
| GET | `/media/video/{asset_id}` (public) | signed | served via `StorageBackend.signed_url` (HMAC for local) |

No HTTP path writes `usage_event` or `video_cost_event` (anti-inflation —
only pipeline jobs do). OpenAPI gains the routes; no existing contract
changes.

---

## 4. Security impact

| Control | V0 treatment |
|---|---|
| **Tenant isolation (app)** | every query filters brand/org; routes `require_permission("video.*")` |
| **Tenant isolation (DB)** | 7 tenant tables added to the RLS policy set (dormant) — RLS readiness preserved |
| **Jobs tenant-scoped** | pipeline skeletons use Phase-0 `@tenant_job` (org + RLS context restored per job) |
| **Secrets** | `GOOGLE_APPLICATION_CREDENTIALS`/`VERTEX_PROJECT`, `ELEVENLABS_API_KEY`, `S3_*` → added to `SECRETS.md` + `validate_production_secrets`, **required only when `video_enabled=true`** (so non-video prod still boots) |
| **No bytes in PG** | Postgres stores only `StorageRef` + metadata; bytes live in S3/local, signed-URL served |
| **Media access** | signed URLs only (HMAC for local, presigned for S3); files outside web root; no public listing |
| **Prompt safety** | `sanitize_prompt_input` on brief + every scene prompt (wired in V0 service even though the stub doesn't call a model) |
| **Audit (every step)** | `ai_audit_events` row per stage transition (action `generate_video`/`generate_reel`, status), **no generated content stored**; `video_cost_event` is the money trail — audit logging preserved for every generation step |
| **Cost caps / org budgets / usage enforcement** | pre-flight estimate + `video_render_daily_cap` + per-org budget cap + `enforce_quota` soft gate (record-only until enforcement flips) — all preserved from Phase 1 |
| **No vendor lock-in** | three ABCs (video/TTS/storage); stub impls in V0; no provider hardcoded anywhere above the `providers/` layer |
| **Gitleaks** | add SA-JSON + ElevenLabs (`sk_...`) + S3 key patterns to `.gitleaks.toml` |

All current security controls (rate limit, Sentry scrubber, JWT hardening,
AUTH_MODE guard) are untouched and continue to apply.

---

## 5. Rollback plan

V0 ships dark; multiple independent off-switches, no behavior change at rest:
1. **`VIDEO_ENABLED=false`** (default) → all endpoints 409, no jobs enqueued, nothing runs. The product is identical to pre-V0.
2. **Provider/backend stay `stub`/`local`** (defaults) → even if the flag were flipped, no external spend (stub providers, local storage).
3. **Migration `0034` reversible** → `alembic downgrade 0033` drops all video tables/policies/seeds and restores the usage CHECK. `subscription`/`invoice`/existing data untouched.
4. **No existing code path depends on the video module** → deleting `modules/video/` has zero impact on the rest of the app (it's purely additive, like the AI-audit module was).

Escalation: flag off → (if needed) revert router registration → (last) downgrade 0034. No data loss at any rung.

---

## 6. Success metrics (V0 acceptance)

- ✅ Migration `0034` applies + is reversible live (apply → downgrade → re-apply), 8 tables + 7 format rows + RLS policies + RBAC perms + quota seeds.
- ✅ The three ABCs + stub impls pass unit tests; the stub pipeline drives a project `draft → ready` end-to-end **with no network call**.
- ✅ The stub pipeline job proves **tenant isolation** (a job sees only its org's rows under RLS) — reuses the Phase-0 harness test.
- ✅ Cost ledger + both usage kinds (`video_generation`, `video_second`) record correctly (stub costs); per-user daily cap + org budget gate enforce in tests.
- ✅ `video_enabled=false` → endpoints 409, **zero change to existing behavior**; full backend suite stays green.
- ✅ Boot guard verified: prod + `video_enabled=true` + missing Vertex/ElevenLabs/S3 secrets → refuses to boot; video-off prod boots fine.
- ✅ RLS policies present-but-dormant for video tables (consistent with readiness posture).

---

## 7. Reuse map (no rewrites)

| Reused | From |
|---|---|
| `@tenant_job` + `enqueue_tenant_job` | Phase 0 |
| `record_metered` + `plan_quota` + usage CHECK pattern | Phase 1 |
| `RenderedVisual` shape (provider/cost/latency/fingerprint) | visuals (→ `video_render`) |
| HMAC signed-URL serving (`media_url`, `media_router`) | visuals (→ `LocalDiskBackend`) |
| `TenantMixin` + RLS readiness (`db/rls`) | tenancy + RLS phase |
| `ai_audit_events` (no content stored) | AI Audit Trail |
| `sanitize_prompt_input` | Prompt sanitization phase |
| `validate_production_secrets` + `SECRETS.md` + `.gitleaks.toml` | Phase S1 |
| DB-backed catalog pattern (`plan`/`plan_quota`) | Phase 1 (→ `video_format`) |
| RBAC permission seed pattern | migration 0014 |

## 8. Task breakdown (for execution after approval)
1. `config.py` — video flags + provider/backend selectors + secrets + caps.
2. Migration `0034_video_foundation` — 8 tables, indexes, RLS policies, format seed, usage CHECK + quota seed, RBAC seed.
3. ORM models + register in `alembic/env.py`; add tables to `db/rls.RLS_TABLES`.
4. `providers/base.py` + `providers/stub.py` + `providers/registry.py`.
5. `tts/base.py` + `tts/stub.py`.
6. `storage/base.py` + `storage/local.py` (+ `s3.py` interface) + `storage/registry.py`.
7. `service.py` (project CRUD + state machine) + `cost.py` + `metering.py` + `formats.py`.
8. `tasks.py` — stub pipeline jobs (`@tenant_job`), register in `ALL_JOBS`.
9. `router.py` (flag-gated) + register in `main.py`.
10. `validate_production_secrets` + `SECRETS.md` + `.gitleaks.toml` updates.
11. Tests — migration reversibility (live), stub pipeline draft→ready, tenant isolation, cost+both-usage-kinds, daily-cap + budget gate, flag-off 409s, boot guard.
12. Gates: pytest + (app imports) + migration apply/rollback evidence.

## 9. Open items deferred to V1 (not V0)
- Real `veo3.py` (Vertex SA long-running op) + `elevenlabs.py` + `s3.py`.
- ffmpeg assembly worker image; voiceover/subtitle passes.
- Frontend video studio.
- Real cost numbers (V0 uses stub estimates).
