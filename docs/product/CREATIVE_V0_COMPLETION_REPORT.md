# Creative Core V0 — Completion Report

> Unified Creative Platform core + Video subsystem, shipped DARK.
> PostgreSQL source of truth · multi-tenant · RLS-ready · additive-only ·
> no rewrites of visuals/content. Date: 2026-06-11.

---

## What shipped

A media-agnostic **Creative Platform core** with **Video as its first
subsystem** — exactly the unified architecture from the review, with
`creative_*` table names chosen now (while empty) so future creative types
(posters/banners/carousels/…) drop in with **no rename migration**.

### Files (new)
- **`aicmo/modules/creative/`** (core): `models.py` (8 tables), `schemas.py`, `service.py` (project CRUD + state machine), `cost.py` (cost ledger + org budget), `metering.py` (both usage kinds + daily cap), `formats.py` (DB catalog), `router.py` (flag-gated `/creative/*` + signed media), `storage/` (base + local + s3-interface + registry).
- **`aicmo/modules/video/`** (subsystem): `models.py` (video_scene, video_render), `tasks.py` (stub pipeline `@tenant_job`), `providers/` (VideoProvider ABC + stub + registry), `tts/` (TTSProvider ABC + stub + registry).
- **Migration `0034_creative_core`** — 10 tables, 7-format seed, 15 RLS policies, usage CHECK += `video_generation`/`video_second`, plan_quota seed, RBAC `video.*` perms + grants.
- **`tests/creative/`** — 7 tests incl. the live end-to-end stub pipeline.

### Files (edited)
- `config.py` — video flags + provider/storage selectors + caps + secrets + boot guard.
- `db/rls.py` — 9 new tenant tables registered for RLS.
- `alembic/env.py` — new models registered.
- `queue/worker.py` — `generate_video_stub` in `ALL_JOBS`.
- `main.py` — creative router + public media router.
- `SECRETS.md`, `.gitleaks.toml`, `.env.example` — Vertex/ElevenLabs/S3.

---

## Decisions honored
1. **Audio** — always-layer TTS (`audio_mode` default `tts_voiceover`); `TTSProvider` abstraction; Veo native audio muted in assembly.
2. **TTS** — `TTSProvider` ABC, ElevenLabs reserved as the V1 impl; stub in V0.
3. **Metering** — **both** `video_generation` (per-video quota) + `video_second` (per-second); cost ledger (`creative_cost_event`) tracks provider cost, storage stage, and render duration.
4. **Storage** — `StorageBackend` (local|s3); Postgres stores only a `StorageRef` (backend+key) — **no bytes in PG**; S3 interface ready for V1.
5. **Veo access** — `VideoProvider` ABC; Veo reserved as the first impl (Vertex SA in V1); selecting `veo3`/`elevenlabs`/`s3` in V0 raises a clear error — **no vendor lock-in**.

## Requirements honored
- ✅ PostgreSQL source of truth (metadata/audit/quota/cost/status/refs).
- ✅ Multi-tenant (`TenantMixin` on every tenant table) + RLS-ready (9 tables in the policy set, dormant).
- ✅ Shared asset storage (`creative_asset` + `StorageBackend`).
- ✅ Shared metering + cost + audit + campaign link (one core, one ledger).
- ✅ No rewrites of visuals/content — they register into `creative_asset` later, additively.
- ✅ Additive migration only; reversibility verified live.
- ✅ Every long-running op async via Arq (`@tenant_job` stub pipeline; submit→poll seam).

---

## Verification evidence

| Gate | Result |
|---|---|
| Migration 0034 applied + **reversibility** (live down→0033→up) | ✅ |
| Creative V0 suite | ✅ 7 passed |
| — live stub pipeline draft→**ready** (asset + cost ledger + BOTH usage kinds, no network) | ✅ |
| — storage sign/verify, stub providers, flag-default-off, boot guard | ✅ |
| RLS test set (now covers creative core, `creative_format` excluded) | ✅ |
| Cross-cutting (rls/tenancy/billing/queue/creative) | ✅ 108 passed |
| **Full backend suite** | ✅ **923 passed**, 0 regressions |
| App imports + 7 `/creative/*` routes registered | ✅ |
| Boot guard: prod + video+veo3 + missing Vertex → refuses; video-off / stub → boots | ✅ |

---

## Dark-launch / rollback posture
- `VIDEO_ENABLED=false` (default) → every `/creative/*` authoring endpoint returns 409; no pipeline runs. Product unchanged.
- Providers/backend default to `stub`/`local` → **no external spend even if the flag were flipped**.
- `alembic downgrade 0033` reverses 0034 (verified); `modules/creative` + `modules/video` are purely additive — deletable with zero impact on the rest of the app.

---

## What V1 fills (the stubs)
- `video/providers/veo3.py` (Vertex AI service account + long-running op, SynthID) and the multi-job poll fan-out (`render_scene` + `poll_render` with `defer_by` backoff — required for real Veo latency).
- `video/tts/elevenlabs.py` (brand voices).
- `creative/storage/s3.py` impl (presigned URLs) + ffmpeg assembly worker.
- Real cost numbers (V0 uses stub estimates).

## Future creative types (the payoff)
Posters/banners/carousels/thumbnails/social posts/reel covers add only a
generator + register a `creative_asset(media_type=image|…, source_kind=…)`
— **zero changes to the core tables, zero rename migration.** That is the
unified Creative Platform the review set out to build.
