# DM Tool — Video Generation Architecture (Google Veo 3)

> Production-grade architecture + implementation roadmap. Design only — no code.
> Roadmap reference: Phase B item #10 (Reels/Shorts video generator).
> PostgreSQL is the system of record. Multi-tenant. Reuse-first.
> Date: 2026-06-11.

---

## 0. Design principles (what we reuse, not rebuild)

This is **net-new capability built on existing rails**. Nothing here is a
rewrite:

| Existing primitive | Reused for video |
|---|---|
| `TenantMixin` (org_id + brand_id NOT NULL) | every video table is tenant-scoped |
| RLS readiness (`db/rls.py`, migration 0032) | new video tables join the RLS policy set |
| Visuals **provider abstraction** (`modules/visuals/render.py`, OpenAI Images) | `VideoProvider` abstraction (Veo 3 first impl) — same pattern |
| `RenderedVisual` model (provider, cost_cents, latency_ms, file_path, prompt_fingerprint) | `video_render` mirrors it + video fields |
| HMAC **signed-URL media serving** (`media_url.py` / `media_router.py`) | video served the same way (no public listing) |
| `media_dir` + `media_signing_secret` + `image_render_daily_cap` config | `video_*` config siblings |
| **Phase 0 job harness** (`enqueue_tenant_job` + `@tenant_job`) | every pipeline stage is a tenant-scoped Arq job |
| **Phase 1 metering** (`record_metered`, `plan_quota`, usage kinds) | new `video_generation` metered kind + cost ledger |
| **AI audit trail** (`ai_audit_events`, action `generate_reel`) | per-stage generation audit, no content stored |
| Prompt sanitiser (`security/prompt_safety.py`) + banned phrases | applied to every prompt that reaches Veo |
| Integrations framework (OAuth + Fernet) | publish stage (Meta/TikTok/YouTube) |

New module: **`apps/api/aicmo/modules/video/`** (separate from `visuals`,
which stays image-only). Follows the standard module layout
(`router/service/schemas/models/prompts/tasks`).

---

## 1. Why Veo 3 shapes the architecture

Veo 3 (via **Vertex AI / Gemini API**) has properties that dictate the design:

| Veo 3 property | Architectural consequence |
|---|---|
| **Asynchronous long-running operation** (submit → poll) | every clip is an Arq job that submits then polls with backoff; never a blocking request |
| **~8 s max per clip** | longer videos (15–60 s reels) are **multi-scene**: storyboard → N clips → stitch |
| **Native audio** (dialogue/SFX/music) | optional; we still support a **separate voiceover + subtitle layer** for brand control + accessibility |
| **Text-to-video + image-to-video** | image-to-video seeds **product commercials** + **UGC** from a brand/product still |
| **16:9 and 9:16, 720p/1080p, 24fps** | format catalog maps platform → aspect/res/duration |
| **SynthID watermark + safety filters** | provenance is automatic; we record it; content safety is layered with our banned-phrase guardrails |
| **Per-second pricing (expensive)** | **cost estimate before generation**, a cost ledger, per-org budget caps, and metering are first-class — not afterthoughts |

**Provider abstraction (critical):** Veo 3 is the *first* `VideoProvider`,
not a hardcoded dependency. The same interface admits Runway/Sora/Kling
later. Mirrors how `visuals` abstracts OpenAI Images.

---

## 2. The generation pipeline (8 stages)

A `video_project` moves through a state machine. Each stage is an
idempotent, tenant-scoped Arq job that, on success, enqueues the next.

```
 brief (Campaign/AI/founder)
   │
   ▼
[1] SCRIPT GEN        LLM → structured script (hook, beats, CTA, VO lines)      → video_project.script
   │
   ▼
[2] STORYBOARD GEN    LLM → ordered scenes (prompt, duration, motion, seed)     → video_scene[]
   │                  (optional) image keyframe per scene via visuals provider
   ▼
[3] VEO 3 GEN         per scene: submit Veo op → poll → download clip           → video_render[] (one per scene)
   │                  (parallel fan-out, bounded concurrency, cost-gated)
   ▼
[4] ASSEMBLY          stitch clips in order (ffmpeg) → base timeline            → video_asset (status=assembling)
   │
   ▼
[5] VOICEOVER         TTS from script VO lines (brand voice id) → audio track   → voiceover_track
   │                  (skipped if Veo native audio chosen)
   ▼
[6] SUBTITLES         from script timing OR forced-alignment → SRT/VTT + burn-in → subtitle_track
   │
   ▼
[7] BRAND KIT         logo bug, color grade, intro/outro card, end CTA, font    → applies brand_kit
   │
   ▼
[8] VARIANTS + A/B    fan-out: alt hooks / CTAs / music / first-3s → N assets   → video_variant[]
   │
   ▼
 READY → (autonomous) PUBLISH → MEASURE → OPTIMIZE
```

Stages 5–7 are **post-production passes** (ffmpeg/audio), not LLM calls —
deterministic, cheap, retto-able. Stage 8 loops back to 3–7 for each
variant.

**Failure policy** (mirrors the rest of DM Tool): any stage can fail
without 5xx-ing the founder — the project lands in a `failed_<stage>`
state with a human-readable reason; partial artifacts are retained for
retry; the founder always sees status, never a crash.

---

## 3. Database schema (PostgreSQL — system of record)

All tables inherit `TenantMixin` (organization_id + brand_id NOT NULL) +
`TimestampMixin`. UUID PKs. JSONB for structured LLM output. **No video
bytes in Postgres** — only metadata + signed-path references (bytes on
disk/S3, served via signed URLs).

### 3.1 `video_project` — the top-level creative
```
id, organization_id, brand_id, user_id
business_profile_id            FK business_profiles
campaign_id                    FK campaign_plans (nullable — autonomous link)
title, brief                   text (sanitised)
platform                       'instagram_reels'|'meta_ads'|'facebook_ads'|
                               'tiktok'|'youtube_shorts'|'ugc_ad'|'product_commercial'
format_spec                    JSONB (aspect, resolution, max_duration_s, fps — from catalog)
objective, goal, tone          text
script                         JSONB  (structured: hook, beats[], cta, vo_lines[])
seed_asset_id                  uuid (nullable — image-to-video seed; product/UGC)
status                         enum (see §3.8)
audio_mode                     'veo_native'|'tts_voiceover'|'silent'
estimated_cost_cents           int   (pre-flight estimate)
actual_cost_cents              int   (rolled up from cost ledger)
ab_group_id                    uuid (nullable — groups variants of one test)
created_at, updated_at
```

### 3.2 `video_scene` — storyboard beats
```
id, video_project_id FK, organization_id, brand_id
scene_index          int  (order)
prompt               text (the Veo prompt for this scene; sanitised)
motion_hint          text ('slow push in', 'handheld', ...)
duration_s           numeric(4,1)  (≤ ~8)
seed_image_path      text (nullable — image-to-video keyframe)
vo_line              text (nullable — the VO for this scene)
status               enum (pending|rendering|done|failed)
```

### 3.3 `video_render` — one Veo clip per scene (mirrors `RenderedVisual`)
```
id, video_scene_id FK, video_project_id FK, organization_id, brand_id, user_id
provider              'veo3'   (the VideoProvider impl)
provider_operation_id text     (Veo long-running operation name — poll key)
prompt                text
prompt_fingerprint    char(64) index   (dedupe / cache)
file_path             text     (downloaded clip; signed-URL served)
mime_type             'video/mp4'
width, height, fps    int
duration_ms           int
has_native_audio      bool
synthid_watermark     bool     (provenance — always true for Veo)
status                enum (submitted|polling|succeeded|failed|content_blocked)
error_class           text (nullable)
cost_cents            int
latency_ms            int
created_at, updated_at
```

### 3.4 `video_asset` — assembled deliverable (per variant)
```
id, video_project_id FK, organization_id, brand_id, user_id
variant_label         text  ('A'|'B'|'control'|...)
file_path             text  (final stitched+VO+subs+brandkit mp4 — signed URL)
poster_path           text  (thumbnail/first-frame)
caption_path          text  (SRT/VTT subtitles file)
aspect_ratio, resolution, duration_ms, fps
audio_mode            text
brand_kit_id          FK brand_kit (nullable)
status                enum (assembling|ready|failed)
checksum              text
created_at, updated_at
```

### 3.5 `video_variant` — A/B test members
```
id, video_project_id FK, ab_group_id, organization_id, brand_id
video_asset_id        FK video_asset
hypothesis            text   ('shorter hook converts better')
variable_changed      text   ('hook'|'cta'|'music'|'first_3s'|'voice')
is_control            bool
published_ref         JSONB (nullable — platform post id once published)
performance           JSONB (nullable — impressions/CTR/ROAS once measured)
```

### 3.6 `brand_kit` — reusable brand application (extends `brands`)
```
id, organization_id, brand_id  (one default per brand)
logo_path, watermark_position
color_primary, color_secondary, color_accent
font_heading, font_body
intro_template_path, outro_template_path, end_card_cta
voice_provider, voice_id        (TTS brand voice)
music_mood, music_track_path
safe_zones                      JSONB (platform-specific text-safe areas)
```
*(`brands.logo_url` already exists from Phase 10.2f — `brand_kit` is the
richer, video-specific layer.)*

### 3.7 `video_cost_event` — cost ledger (append-only)
```
id, organization_id, brand_id, video_project_id FK, video_render_id (nullable) FK
stage           'veo_clip'|'tts'|'asr'|'image_seed'|'storage'|...
provider        'veo3'|'elevenlabs'|'openai'|...
units           numeric    (video seconds / characters / images)
unit_cost_cents numeric
cost_cents      int
occurred_at
```
Distinct from billing `usage_event`: this is the **money ledger** (what we
paid providers); `usage_event` is the **customer's metered quota**. Both
roll up per org.

### 3.8 Status enum (project state machine)
`draft → scripting → storyboarding → rendering → assembling →
post_processing → ready → published` plus terminal
`failed_<stage>` and `canceled`. Drives the queue + the UI status chip.

### 3.9 Migrations + RLS
- One additive migration (`00XX_video_generation`) creates the tables.
- Every table is added to `db/rls.RLS_TABLES` + gets a `tenant_isolation_*`
  policy (org-scoped) in the RLS migration set — so video inherits the
  same dormant-until-activated DB isolation as leads/campaigns/content.
- Indexes: `(brand_id, created_at DESC)` on `video_project`,
  `(video_project_id, scene_index)` on `video_scene`,
  `(provider_operation_id)` on `video_render` (poll lookup),
  `(organization_id, occurred_at)` on `video_cost_event`.

---

## 4. Provider abstraction (Veo 3 first)

`modules/video/providers/base.py` — `VideoProvider` ABC:
```
submit(prompt, *, aspect, resolution, duration_s, seed_image=None,
       audio=False, negative_prompt=None) -> ProviderOperation
poll(operation) -> ProviderStatus            # pending | done(uri) | failed | blocked
download(uri) -> bytes                        # → stored, signed-served
estimate_cost(duration_s, resolution) -> cents
```
`providers/veo3.py` — the first impl (Vertex AI / Gemini long-running op +
SynthID metadata). `providers/registry.py` selects by
`video_default_provider` config — identical to the integrations registry
pattern. A stub provider backs tests (no real API calls in CI).

---

## 5. Queue architecture (Arq)

Built entirely on the **Phase 0 tenant-job harness** — every job carries
the tenant envelope and runs under the org's RLS context.

### 5.1 Jobs (each `@tenant_job`, registered in `ALL_JOBS`)
```
video.generate_script        (project_id)            → script, enqueue storyboard
video.generate_storyboard    (project_id)            → scenes, enqueue per-scene render
video.render_scene           (project_id, scene_id)  → submit Veo op, enqueue poll
video.poll_render            (render_id)             → poll; reschedule (defer_by backoff) or finalize
video.assemble               (project_id, variant)   → ffmpeg stitch
video.add_voiceover          (asset_id)
video.add_subtitles          (asset_id)
video.apply_brand_kit        (asset_id)
video.generate_variants      (project_id)            → fan-out A/B
video.publish                (variant_id)            → integrations (Phase C)
```

### 5.2 Veo polling pattern
`render_scene` submits the op + stores `provider_operation_id`, then
enqueues `poll_render`. `poll_render` checks status; if pending it
re-enqueues itself with `defer_by` exponential backoff (e.g. 15s → 30s →
60s, capped, with a max-attempts deadline → `failed`). Idempotent: keyed
on `video_render.status` so a double-fire is a no-op. This is the standard
way to ride a long-running operation through Arq without holding a worker.

### 5.3 Concurrency + cost gating
- **Bounded fan-out**: a project with N scenes doesn't submit N Veo ops at
  once unbounded — a per-org semaphore (Arq `job_id` dedupe + a DB
  in-flight count) caps concurrent expensive renders.
- **Pre-flight cost gate**: before stage 3, `estimate_cost` × scenes is
  checked against the org's remaining video budget + plan quota. Over →
  the project parks in `blocked_budget` with an upgrade CTA (never a
  surprise bill).
- **Cancellation**: a founder/ops can cancel → in-flight ops are
  abandoned, status `canceled`, no further spend.

---

## 6. API endpoints

All under `/api/v1/video`, tenant + permission gated. New permission slug
`video.create` (seeded into RBAC alongside `content.create`).

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/video/projects` | `video.create` | create a project from a brief; returns estimate + status |
| GET | `/video/projects` | `video.read` | list (brand-scoped, paginated) |
| GET | `/video/projects/{id}` | `video.read` | full status + scenes + assets + cost |
| POST | `/video/projects/{id}/start` | `video.create` | confirm estimate → kick off pipeline (enqueue) |
| POST | `/video/projects/{id}/variants` | `video.create` | generate A/B variants |
| POST | `/video/projects/{id}/cancel` | `video.create` | cancel in-flight |
| GET | `/video/projects/{id}/cost` | `video.read` | cost breakdown (ledger rollup) |
| GET | `/video/assets/{id}/signed-url` | `video.read` | short-lived signed playback URL |
| GET | `/media/video/{asset_id}` (public) | signed | stream the file (HMAC + expiry — reuses `media_url`) |
| POST | `/video/projects/{id}/publish` | `video.publish` | (Phase C) push a variant to a connected platform |

No HTTP endpoint ever writes `usage_event` or `video_cost_event` directly
(anti-inflation — same rule as billing). Cost/usage are written only by
the pipeline jobs.

---

## 7. Cost tracking + usage metering

Two separate ledgers, both PostgreSQL, both per-org:

**Cost (what WE pay providers)** — `video_cost_event`:
- Every Veo clip, TTS call, ASR call, image seed writes a row with units ×
  unit_cost. Rolled up to `video_project.actual_cost_cents` +
  org/month dashboards. Drives gross-margin reporting and the per-org
  budget cap.

**Usage (what the CUSTOMER's plan allows)** — reuses Phase 1:
- New metered kind **`video_generation`** (1 per finished project) and/or
  **`video_second`** (finer; for fair-use on duration). `plan_quota` rows
  per plan (DB-configurable, no deploy). `record_metered` after a project
  reaches `ready`. Soft-gated by `enforce_quota` (record-only until
  enforcement flips on, exactly like content/ads).
- Video is expensive → its own daily/monthly caps: config
  `video_render_daily_cap` (per user, like the 20/day image cap) +
  per-org budget cents cap. These are **abuse/cost controls**, independent
  of plan quota.

**Pre-flight estimate** is shown before `start` so the founder confirms
"~$X for this 30s reel" — never a silent charge.

---

## 8. Security, tenant isolation, audit

| Control | Mechanism |
|---|---|
| **Tenant isolation (app)** | every query filters `brand_id`/`organization_id`; routes `require_permission("video.*")` |
| **Tenant isolation (DB)** | new tables in the RLS policy set (org-scoped, dormant-until-activated per `RLS_ACTIVATION.md`) |
| **Jobs stay tenant-scoped** | Phase 0 `@tenant_job` restores org/RLS context inside every pipeline job |
| **Prompt safety** | `sanitize_prompt_input` on brief + every scene prompt before it reaches Veo; banned-phrase guardrails |
| **Content safety** | Veo's built-in safety filters + our policy; `content_blocked` is a first-class render status |
| **Provenance** | SynthID watermark recorded on every `video_render`; surfaced in the UI + audit |
| **Media access** | signed URLs only (HMAC + expiry, reuses `media_url`); no public listing; files outside the web root |
| **Secrets** | `VEO_API_KEY` / Vertex creds + any TTS key → `SECRETS.md` + prod boot guard (required only when video enabled) |
| **Cost abuse** | pre-flight estimate + per-org budget cap + per-user daily cap + bounded fan-out → no runaway spend |
| **Audit** | `ai_audit_events` row per generation (action `generate_reel`/`generate_video`, model `veo3`, status) — **no generated content stored**; `video_cost_event` is the money trail |
| **PII / brand assets** | seed images + brand kit are tenant-scoped + signed-served; encrypted at rest when on S3 (KMS) |
| **No card data, no model-training leakage** | provider calls send only the sanitised prompt + opt-in seed image; logged metadata excludes the rendered bytes |

---

## 9. Platform / format support

A `video_format` catalog (DB-backed, like `plan` — tunable without deploy)
maps each platform to a spec. The pipeline reads it to set aspect,
resolution, max duration, scene count, and a style preset.

| Format | Aspect | Res | Duration | Seeding | Style preset |
|---|---|---|---|---|---|
| Instagram Reels | 9:16 | 1080×1920 | 15–60 s | optional | hook-first, fast cuts, captions burned-in |
| TikTok-style | 9:16 | 1080×1920 | 9–60 s | optional | native/UGC energy, trending pacing |
| YouTube Shorts | 9:16 | 1080×1920 | ≤60 s | optional | retention hook, loopable |
| Meta Ads (feed) | 4:5 / 1:1 | 1080×1350 / 1080² | ≤15 s | optional | clear offer + CTA card |
| Facebook Ads | 4:5 / 1:1 / 16:9 | per placement | ≤15 s | optional | benefit-led, CTA end card |
| UGC advertisement | 9:16 | 1080×1920 | 15–30 s | **image-to-video** (real person/product still) | handheld, authentic, talking-style VO |
| Product commercial | 16:9 / 1:1 | 1080p | 10–30 s | **image-to-video** (product shot) | polished, studio motion, music-led |

For durations > ~8 s, the storyboard stage produces ⌈duration / 8⌉ scenes
that are stitched (stage 4). Image-to-video seeds (UGC, product) come from
the existing visuals render or an uploaded brand asset.

---

## 10. Future autonomous workflow

The pipeline is the **Creative** node of the autonomous loop (roadmap
Phases C–F). It plugs in without rework because every stage is already a
tenant-scoped job:

```
CAMPAIGN          Opportunity/Coach picks a video brief
  → CREATIVE       this pipeline → ready video_asset(s) + A/B variants
  → PUBLISH        integrations (Meta/TikTok/YouTube write APIs) → published_ref
  → MEASURE        performance sync → video_variant.performance (ROAS/CTR)
  → OPTIMIZE       Learning Lab compares variants → regenerate the winner's
                   pattern as the next campaign's seed (closes the loop)
```

- **Campaign link**: `video_project.campaign_id` ties a video to a
  `campaign_plan`; the autopilot (Phase 2) can request a video brief.
- **Publish**: reuses the integrations OAuth framework; write-scope tokens
  are Fernet-encrypted; publishing is **approval-gated per brand** before
  the first autonomous post (no surprise posting).
- **Measure → Optimize**: variant `performance` JSONB feeds the existing
  Learning Lab + recommender; the winning variant's `variable_changed`
  becomes a prior for the next generation. Human approval gate stays until
  trust is established.

---

## 11. Implementation roadmap (incremental, each ships independently)

| Sub-phase | Scope | Ships when |
|---|---|---|
| **V0 — Foundation** | `modules/video/`, schema migration, `VideoProvider` ABC + **stub**, config flags (`video_enabled`, caps), RLS policies, permission seed. No real Veo. | tables + tests green, flag off |
| **V1 — Single-clip Veo** | Veo3 provider (text-to-video, 9:16, ≤8 s), `render_scene`+`poll_render` jobs, signed serving, cost ledger + metering, pre-flight estimate. One-scene reel. | first real Veo clip, metered |
| **V2 — Multi-scene** | script→storyboard→N clips→ffmpeg stitch. 15–60 s reels. | longer videos |
| **V3 — Audio + subtitles** | TTS voiceover layer + subtitle generation/burn-in. | branded VO + captions |
| **V4 — Brand kit** | `brand_kit` application (logo, color, intro/outro, end card). | on-brand output |
| **V5 — Variants + A/B** | variant fan-out, A/B grouping, performance schema. | testable creative |
| **V6 — Publish + autonomy** | integrations publish + measure + optimize loop (depends on Phases C–F). | closed loop |

Dependencies: V1+ depends on **Phase 0 (jobs)** ✅ and **Phase 1
(metering)** ✅ — both already shipped. V6 depends on the live integrations
(roadmap Phase C).

---

## 12. Risks + mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Runaway Veo spend | High | pre-flight estimate + per-org budget cap + per-user daily cap + bounded fan-out + cost ledger alerting |
| Long/variable Veo latency | Medium | async poll-with-backoff; founder sees live status; deadline → graceful `failed` |
| Unsafe/off-brand generation | Medium | prompt sanitiser + banned phrases + Veo safety + `content_blocked` status + brand-kit constraints + human review before publish |
| Provider lock-in | Medium | `VideoProvider` ABC — Veo is swappable; stub backs tests |
| Storage growth (video is large) | Medium | signed-URL serving now; S3 + lifecycle/TTL on old renders post-MVP (the `MEDIA_BACKEND` swap is already designed in visuals) |
| ffmpeg in the worker (assembly) | Low | runs in the Arq worker image, not the API; isolated; retried idempotently |
| Tenant leakage via shared media dir | High | files keyed by tenant + signed URLs + (when RLS active) DB-enforced row access; never list across tenants |
| Autonomous mis-post | High | per-brand approval gate before first auto-publish; full audit + reversible |

---

## 13. Success metrics
- Time-to-first-video per founder; % briefs that reach `ready`.
- Gross margin per video (cost ledger vs plan price) — must stay positive.
- Veo render success rate; p95 end-to-end project time.
- Variant adoption + (Phase C) measured ROAS lift of generated video vs static.
- 0 cross-tenant media access; 0 budget-cap breaches; 100% of generations audited.

---

## 14. Open decisions (for sign-off before V0 build)
1. **Audio default** — Veo native audio vs always-layer our TTS voiceover? (Recommend: TTS voiceover default for brand-voice control; native audio as an option.)
2. **TTS provider** — ElevenLabs vs Google vs OpenAI for brand voices (affects cost ledger + secrets).
3. **Metering unit** — per finished video, per second, or both? (Recommend: per-video for the quota, per-second tracked in the cost ledger.)
4. **Storage** — go straight to S3 for video (large files) rather than local disk? (Recommend: yes for V1 — video sizes outgrow local fast.)
5. **Veo access path** — Vertex AI (service-account) vs Gemini API key (affects auth + secrets).
