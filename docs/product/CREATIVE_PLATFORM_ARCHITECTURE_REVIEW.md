# Creative Studio — Unified Platform Architecture Review

> **Extended (2026-06-11):** the platform evolved into an editable,
> layer-based Creative Studio (Canva-style) — see
> `CREATIVE_STUDIO_ARCHITECTURE.md`. That doc adds `creative_design` /
> `creative_design_revision` / `brand_asset` on top of the core below;
> everything in this review remains valid and additive.

> Review + recommendation. No code, no implementation.
> Decision gate **before** building Video V0 — taken now while the video
> tables are still empty (the cheapest possible moment to choose).
> Date: 2026-06-11.

---

## 0. Verdict (up front)

**Video V0 should NOT be a standalone module. It should be the first
media subsystem of a unified Creative Platform core.**

The evidence is already in the codebase: the creative surfaces overlap
*today*, and a third independent module would triple the duplication of
brand kit, asset library, storage, metering, cost, publishing, and audit.
Because the video tables are **empty (not yet built)**, we can adopt the
unified names *now* at zero data-migration cost. The required change is a
**rename + generalization of 5 tables in the V0 design** — listed
explicitly in §6. Do that, and Video V0 slots cleanly into the Creative
Platform with **no future migration** to "promote" it.

---

## 1. Current state — the fragmentation is real

| Module | Produces | Table(s) |
|---|---|---|
| `visuals` | `VisualType = ad_creative \| carousel \| reel \| thumbnail` (images via OpenAI Images) | `generated_visuals`, `rendered_visuals` |
| `content` | `ContentType = social_post \| reel \| carousel \| ad_copy` (text/scripts) | `generated_content` |
| `video` (V0 designed) | Veo videos | `video_project`, `video_scene`, `video_render`, `video_asset`, … |

**The overlap is already a smell:** `carousel` and `reel` are *both* a
visuals type AND a content type — the same creative concept split across
two modules with two tables and two result-card UIs. The `/library` page
already exists but has no single table to back a true cross-media library.

If we add `video_*` as a third silo, every shared concern
(brand kit, library, storage, metering, cost, publish, audit, campaign
link) gets a third parallel implementation. That is the exact debt the
constitution says to avoid.

---

## 2. The 11 surfaces → a clean taxonomy

The 11 requested surfaces are **not 11 modules** — they are a small set of
**media types** × **creative types**, plus **shared horizontal services**.

| # | Surface | Media type | Creative type | Generator |
|---|---|---|---|---|
| 1 | Poster | `image` | `poster` | image (visuals provider) |
| 2 | Banner | `image` | `banner` | image |
| 3 | Carousel | `carousel` (N images) | `carousel` | image ×N |
| 4 | Thumbnail | `image` | `thumbnail` | image |
| 5 | Social Post | `composite` (text+image) | `social_post` | content + image |
| 6 | Reel Cover | `image` | `reel_cover` | image |
| 7 | Video (Veo) | `video` | `video` | **video subsystem** |
| 8 | **Brand Kit** | — | — | **shared service** |
| 9 | **Asset Library** | — | — | **shared store** |
| 10 | **Template System** | — | — | **shared service** |
| 11 | **Multi-format Exports** | — | — | **shared service** |

So: **3 media types** (`image`, `carousel`, `composite`, `video`) drive
**~7 creative types**, and **4 of the 11 are horizontal services every
creative type consumes.** That is the architecture.

---

## 3. The unified Creative Platform architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  CREATIVE PLATFORM CORE   (modules/creative/ — media-agnostic)         │
│                                                                        │
│   creative_project   ── the brief/job (creative_type, media_type,      │
│                          campaign_id, status, cost, A/B group)         │
│   creative_asset     ── the UNIFIED ASSET LIBRARY row (one per          │
│                          deliverable, any media; storage_ref +          │
│                          source_kind/source_id pointer + published_ref) │
│   creative_variant   ── A/B variants of a project                       │
│   creative_cost_event── shared cost ledger (provider + storage + dur.)  │
│   creative_format    ── DB catalog: aspect/res/duration/style/seeding   │
│   creative_template  ── reusable templates (any media)                  │
│   creative_export    ── multi-format export records (resize/transcode)  │
│   brand_kit          ── logo/colors/fonts/voice/intro-outro (shared)    │
│                                                                        │
│   SHARED HORIZONTALS (services, not tables):                           │
│     storage   StorageBackend (local|s3)  ── no bytes in PG             │
│     metering  billing.record_metered + plan_quota                      │
│     cost      creative_cost_event writer + per-org budget              │
│     publish   integrations OAuth → creative_asset.published_ref        │
│     audit     ai_audit_events (per stage, no content stored)           │
│     campaign  creative_project.campaign_id → campaign_plans            │
└──────────────────────────────────────────────────────────────────────┘
        ▲                    ▲                     ▲
        │                    │                     │
┌───────┴───────┐   ┌────────┴────────┐   ┌────────┴─────────┐
│ IMAGE          │   │ CONTENT          │   │ VIDEO (Veo)       │
│ subsystem      │   │ subsystem        │   │ subsystem         │
│ (visuals)      │   │ (content)        │   │ (modules/video)   │
│ rendered_visual│   │ generated_content│   │ video_scene       │
│ ImageProvider  │   │ (LLM)            │   │ video_render      │
│ poster/banner/ │   │ social_post/     │   │ VideoProvider(Veo)│
│ thumbnail/cover│   │ caption/script   │   │ TTSProvider       │
└────────────────┘   └──────────────────┘   └───────────────────┘
   each subsystem REGISTERS its output as a creative_asset
```

**Key design move — the Asset Library is the unification point.**
`creative_asset` is a media-agnostic registry row per deliverable. Each
subsystem keeps its native domain table (`rendered_visuals`,
`generated_content`, `video_render`) and **additively registers** a
`creative_asset` pointing at it (`source_kind`, `source_id`, `storage_ref`).
The library, exports, A/B, publishing, campaign attribution, and the
`/library` UI all operate on `creative_asset` — **one surface, every
media type** — without rewriting the existing generators.

This is what makes the unification **incremental, not a rewrite**:
- Video V0 builds *natively* on the core (greenfield → free).
- `visuals` + `content` keep their tables and *additively* register
  creative_assets later (a thin insert, no schema break) — roadmap item,
  not a prerequisite.

---

## 4. How the shared horizontals satisfy your requirements

| Requirement | Where it lives in the core |
|---|---|
| PostgreSQL source of truth | all metadata/status/cost/quota/audit/refs in PG; only bytes in S3 |
| Multi-tenant | every core table `TenantMixin` (org_id + brand_id NOT NULL) |
| RLS-ready | all core tables in `db/rls.RLS_TABLES` + dormant policies |
| Shared asset storage | `StorageBackend` (local|s3) + `creative_asset.storage_ref` |
| Shared metering | `billing.record_metered` + `plan_quota` (per-media usage kinds) |
| Shared cost tracking | `creative_cost_event` (provider + storage + duration), one ledger |
| Shared publishing | integrations OAuth → `creative_asset.published_ref` (any media) |
| Shared audit trail | `ai_audit_events` per stage (no content stored) |
| Shared campaign integration | `creative_project.campaign_id → campaign_plans` |

Every one of these is **defined once in the core** and consumed by all
media subsystems — that is the whole point of choosing "subsystem" over
"standalone."

---

## 5. Recommendation

1. **Create a `modules/creative/` core** carrying the 8 shared tables +
   the storage/metering/cost/publish/audit/campaign services.
2. **Build Video V0 as the `video` subsystem of that core**, not as a
   standalone module. Video contributes only the genuinely video-specific
   tables (`video_scene`, `video_render`) + the `VideoProvider`/`TTSProvider`
   abstractions.
3. **Do the table renames now** (§6) — while empty — so no future
   "promote-video-into-creative" migration is ever needed.
4. **Leave `visuals` and `content` exactly as they are.** They join the
   library later via additive `creative_asset` registration (a separate,
   non-breaking roadmap item). No rewrite, honoring the constitution.

This gives you the unified Creative Platform *architecture* immediately,
with Video V0 as its proof-of-pattern, while spending **zero** on
rewriting working modules.

---

## 6. Schema changes to make NOW in V0 (to avoid future migrations)

The V0 design (`VIDEO_V0_TECHNICAL_DESIGN.md`) is **~80% already aligned**
— `brand_kit`, `StorageRef`, `StorageBackend`, the cost ledger concept,
and the campaign link are all media-agnostic. Five things are
video-prefixed and must be generalized **before** the V0 migration runs,
because renaming a populated table later is the exact painful migration we
want to avoid:

| V0 (standalone) name | → Creative-core name | Change |
|---|---|---|
| `video_project` | **`creative_project`** | add `creative_type` (poster/banner/carousel/thumbnail/social_post/reel_cover/video) + `media_type` (image/carousel/composite/video) discriminators; video is just one value |
| `video_asset` | **`creative_asset`** | add `media_type`, `creative_type`, `source_kind` + `source_id` (polymorphic pointer to the native render row), `published_ref` JSONB, `storage_ref`. This becomes the unified Asset Library. |
| `video_variant` | **`creative_variant`** | media-agnostic A/B; FK → `creative_asset` |
| `video_cost_event` | **`creative_cost_event`** | add `media_type`; one ledger for image + video + tts + storage |
| `video_format` | **`creative_format`** | a poster also has aspect/dimensions — formats span all media |

**Keep video-specific (correctly):** `video_scene`, `video_render` — these
are genuinely video-only (scenes, Veo operations) and reference
`creative_project` / `creative_asset`. The image subsystem will have its
own native render table (`rendered_visuals`, already exists); both register
into `creative_asset`.

**Also create now (empty, cheap insurance):** `creative_template`,
`creative_export`. Adding an empty table later is a trivial migration, but
creating them now keeps the core's RLS policy set + module shape complete
and lets V0's tests pin the full contract. (Optional — flag if you'd
rather defer; the *renames* above are the non-negotiable part.)

**Metering kinds:** no change — Phase 1's `generation` kind already covers
image/content creatives; `video_generation` + `video_second` stay distinct
because video cost/quotas differ. Both roll up per org as designed.

**RLS:** register the renamed `creative_*` tables (not `video_*`) in
`db/rls.RLS_TABLES`.

Net effect: the V0 migration creates `creative_project`, `creative_asset`,
`creative_variant`, `creative_cost_event`, `creative_format`, `brand_kit`,
`creative_template`, `creative_export` (the core) + `video_scene`,
`video_render` (the video subsystem). **When posters/banners/carousels
arrive, they add at most a thin generator + register into `creative_asset`
— zero changes to the core tables, zero rename migration.**

---

## 7. Proof that Video V0 then fits cleanly (no future migration)

Walk each future surface against the renamed core:

- **Poster / Banner / Thumbnail / Reel Cover** → `creative_project(media_type=image, creative_type=…)` → image generator → `creative_asset(source_kind='rendered_visual')`. ✅ no core change.
- **Carousel** → `creative_project(media_type=carousel)` → N image renders → one `creative_asset` + slide children. ✅ no core change.
- **Social Post** → `creative_project(media_type=composite)` → content + image → `creative_asset`. ✅ no core change.
- **Video** → `creative_project(media_type=video)` → `video_scene`/`video_render` → `creative_asset(source_kind='video_render')`. ✅ this IS V0.
- **Brand Kit** → `brand_kit` already shared. ✅
- **Asset Library** → `creative_asset` is it. ✅
- **Template System** → `creative_template` (created now). ✅
- **Multi-format Exports** → `creative_export` rows + `StorageBackend` re-encode. ✅
- **Publishing** → `creative_asset.published_ref` (any media). ✅
- **Campaign integration** → `creative_project.campaign_id`. ✅

Every surface lands on existing core tables with only a new generator and
new enum values (`creative_type` is a string, not a DB enum, so adding
`poster` is a code change, not a migration — same pattern as the plan/
format catalogs). **No core table is altered or renamed after V0.** That
is the proof.

---

## 8. Risks of NOT doing this now

| If we ship video standalone | Consequence |
|---|---|
| 3rd parallel brand-kit / library / cost / publish | triple maintenance + inconsistent behavior across media |
| `/library` can't show video + images together | the unified library you asked for is impossible without a later rename-with-data migration |
| Renaming `video_asset → creative_asset` post-data | a high-risk migration over a hot, S3-referencing table |
| A/B + campaign attribution per-module | no cross-media campaign reporting |

Cost of doing it now: **a naming decision on empty tables.** That asymmetry
is the entire argument.

---

## 9. What we explicitly do NOT do now (scope discipline)

- **No rewrite of `visuals` or `content`.** They keep their tables; they
  register into `creative_asset` as a later additive roadmap item.
- **No real poster/banner generators yet.** V0 still ships only the video
  subsystem (dark) on top of the core. The core just gets media-agnostic
  *names* so the others drop in later.
- **No frontend Creative Studio unification yet.** The `/library` UI
  upgrade to a cross-media grid is a later pass.

---

## 10. Recommended next step

**Update the Video V0 technical design with the §6 renames, then build
V0 as the `creative` core + `video` subsystem** (one migration `0034`,
dark-launched, reversibility-verified). Everything else in the V0 design —
the three provider abstractions, flags, RLS, metering, audit, boot guard,
test plan — stands unchanged; only the 5 table names + 2 added core tables
differ.

Net: you get the **unified Creative Platform architecture as the
foundation**, with Video V0 as its first proven subsystem, at no extra
build cost and no future migration debt.
