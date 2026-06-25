# DM Tool — Creative Studio Architecture (Editable, Layer-Based)

> Evolution of the Creative Core into an AI-powered, Canva-style editable
> Creative Studio. Extends (does not replace) `CREATIVE_PLATFORM_
> ARCHITECTURE_REVIEW.md` and the shipped Creative Core V0.
> PostgreSQL system of record · multi-tenant · RLS-ready · metered ·
> additive-only. Date: 2026-06-11.

**Goal:** combine Canva (layer editor, templates, brand kit), Adobe Express
(one-click resize/export), Jasper (AI copy + natural-language editing), and
Meta Creative Hub (per-platform formats + campaign integration) — while
staying wired into DM Tool's campaign generation, publishing, analytics,
and optimization loop.

> 🤝 **COLLABORATION INVARIANT — `HUMAN_AI_COLLABORATION_INVARIANT.md`.**
> AI Mode (AI creates), Guided Mode (AI modifies), and Pro Mode (human
> modifies) all operate on the **same `creative_design`** via **one** write
> path (`apply_revision`) — no mode-specific code paths. **Nothing mutates
> a design in place; every action appends a `creative_design_revision`.**
> That single mechanism yields undo/redo, history, branching, A/B, approval
> workflows, and team collaboration. Core capability from CS1, not a
> future enhancement.

> ⚠️ **POSITIONING CORRECTION — read `OUTCOME_DRIVEN_ALIGNMENT.md` first.**
> DM Tool is an AI **Growth Platform**, not a design generator. The Studio
> below is the **execution engine**, not the front door: users state
> business objectives ("I need more restaurant customers"); the Strategy
> Engine derives the campaign and invokes these composers. Creative types
> (poster/banner/reel/video/…) are implementation details that Simple Mode
> never surfaces as choices. The primary object chain is
> `growth_objective → campaign_plans → creative_project → creative_asset →
> publish → measure → optimize`. Two doc-level corrections apply:
> (1) templates are **generative** (layout primitives parameterized by
> industry/audience/objective/platform/brand), never category galleries;
> (2) direct asset-type creation survives only as a Pro-mode escape hatch.
> Everything else in this document stands unchanged.

---

## 0. The one architectural shift

**V0 (shipped):** AI generates → bytes in storage → `creative_asset` points
at the file. The file is the deliverable. **Not editable.**

**Studio (this doc):** AI generates → an editable **design document**
(layers, JSONB, in PostgreSQL) → the file is merely a **render** of that
document. Every AI output — poster, banner, carousel, social post, reel,
video ad — is born editable, because the AI composes *layers*, not flat
pixels.

```
V0:      brief ──AI──▶ bytes ──▶ creative_asset (final, frozen)

Studio:  brief ──AI──▶ creative_design (layers, editable, versioned)
                          │  ▲
                          │  └── user edits / AI edits (NL instructions)
                          ▼
                       render ──▶ creative_asset (a render of revision N)
                          ▼
                       exports (multi-format, auto-resized)
```

Everything else from V0 survives unchanged: the provider abstractions
(Video/TTS/Image), StorageBackend, cost ledger, metering, RLS readiness,
flags, the unified Asset Library. The studio is **additive layers on the
same core** — the bet made in the architecture review pays off here.

### 0.1 The Editability Invariant (a hard rule for every composer)

> **Every creative — poster, banner, carousel, social post, ad, thumbnail,
> reel, video, brochure, flyer, email, landing-page asset — is produced as
> a `creative_design` (editable layer document) FIRST. The rendered
> image/video is only an *output* of that document, never the primary
> object. No composer may write a flat `creative_asset` without an owning
> `creative_design`. The design is the source of truth; the file is a
> cache.**

This is enforced structurally, not by convention:
- A `creative_asset` row's `design_id` is **required** for any
  studio-generated creative (nullable only for legacy V0 rows and raw
  uploads). The render job refuses to produce an asset that doesn't
  reference a design + revision.
- The image/video providers (Veo, OpenAI Images, …) **never produce the
  final deliverable directly** — they produce *layer content*
  (backgrounds, subjects, clips) that the composer places into a design.
  Headlines, logos, CTAs, subtitles are always separate editable layers,
  never baked into a generated pixel. That separation is precisely what
  keeps a generated poster as editable as a blank one.

So "do not store posters/reels/videos as final files only" is an
invariant the architecture cannot violate: there is no code path from a
brief to a `creative_asset` that does not pass through a `creative_design`.

### 0.2 Capability coverage (every required user action → mechanism)

| User can… | Mechanism | Acts on |
|---|---|---|
| **Edit text** | direct edit (PUT design) or AI edit (NL → EditOps) | `text` layer props |
| **Replace images** | swap source (library / upload / regenerate) → `update_layer` | `image`/`background` layer `storage_key` or `source_id` |
| **Change colors** | edit color prop, or re-point a brand token, or AI edit | layer `color`/`fill` + `brand:*` tokens |
| **Resize for platforms** | export engine auto-layout pass (anchors + safe zones) | the design → per-`creative_format` render |
| **Create variants** | fork design → tweak one variable → `creative_variant` | a copy of the design |
| **Regenerate sections** | targeted regenerate (§5.1) by layer or `role` | one layer/role/scene, rest untouched |
| **Export multiple formats** | `POST /designs/{id}/export {format_slugs}` fan-out | the design → N `creative_export` rows |
| **Platform-specific versions** (LinkedIn / IG Story…) | **Creative Transform** `reformat` (`POST /designs/{id}/transform`) | derives a NEW design at the target format + re-voiced copy |
| **Media transforms** (poster→carousel→reel) | **Creative Transform** `recompose`/`remediate` | derives a NEW design w/ changed page count / `media_type` |
| **Style variants** ("luxury", "modern") | **Restyle** (`POST /designs/{id}/restyle`) — re-derives the visual system, keeps message + objective | a new design / fork set |
| **Replace logos · change fonts · resize elements** | `update_layer` (logo `brand_asset` ref / `font_family` / geometry) | the targeted layer |
| (also) **Reorder / show-hide / lock / animate** | `reorder` / `update_layer` (visible/locked/animation) | any layer |
| (also) **Re-brand** | swap active `brand_kit` → tokens re-resolve at render | every `brand:*` reference |

> **Export vs Transform:** *export* renders the **same** design to a format
> (dimensions only). *Transform* derives a **new** design that may change
> page count or media type (poster→carousel→reel). Both detailed in
> `OUTCOME_TO_CREATIVE_SYSTEM.md` §6 — the canonical contract that also
> sets the **No-Template-Categories invariant** (templates are generated
> from design primitives, never industry-tagged catalogs).

Every one of these works identically across **poster, banner, carousel,
social post, ad, thumbnail, reel, video** (and future brochure / flyer /
email / landing-page assets) because they are all the *same*
`creative_design` object differing only in `media_type`, page count, and
which layer types are present. One editor, one render engine, one export
engine — all creative types.

---

## 1. The layer-based design model

### 1.1 `creative_design` — the editable source of truth (PostgreSQL)

A design is a JSONB document validated by Pydantic (constitution rule:
structured outputs everywhere; the LLM never emits free-form design data).

```jsonc
{
  "version": 1,
  "canvas": { "width": 1080, "height": 1920, "background": "#FFFFFF" },
  "pages": [                       // 1 page = poster; N pages = carousel
    {                              // or video timeline (page = scene)
      "id": "pg_1",
      "duration_ms": 8000,         // null for static media
      "layers": [
        { "id": "ly_1", "type": "image",
          "x": 0, "y": 0, "w": 1080, "h": 1920, "z": 0,
          "rotation": 0, "opacity": 1.0, "locked": false, "visible": true,
          "props": { "storage_key": "org/.../bg.png", "fit": "cover",
                     "filters": { "brightness": 1.0 } } },
        { "id": "ly_2", "type": "text",
          "x": 80, "y": 1400, "w": 920, "h": 220, "z": 10,
          "props": { "text": "Monsoon Sale — 40% Off",
                     "font_family": "brand:heading", "font_size": 72,
                     "color": "brand:primary", "align": "center",
                     "line_height": 1.1, "weight": 700 } },
        { "id": "ly_3", "type": "video",          // video subsystem layer
          "props": { "source_kind": "video_render", "source_id": "<uuid>",
                     "trim_start_ms": 0, "trim_end_ms": 8000, "volume": 0 } },
        { "id": "ly_4", "type": "audio",
          "props": { "storage_key": "org/.../voiceover.mp3", "volume": 1.0 } },
        { "id": "ly_5", "type": "shape",
          "props": { "shape": "rect", "fill": "brand:accent", "radius": 24 } }
      ]
    }
  ]
}
```

Design rules that make this safe and brand-true:
- **Layer types are a closed set**: `text | image | icon | shape | video |
  audio | group`. Props per type are a validated Pydantic schema — no raw
  HTML, no scripts, no arbitrary keys. (Renderer security depends on this
  — §9.)
- **Every layer carries a semantic `role`** (closed set): `background |
  logo | headline | subhead | body | cta | product | decoration | subtitle`.
  Type says *how it renders*; role says *what it means*. A background can
  be an image, a flat shape, or a video; a logo is an image with
  `role: "logo"`. Roles are what brand-kit swaps, AI edits, and section
  regeneration target ("replace the logo", "regenerate the background")
  — and what makes a design re-brandable and auto-resizable with intent
  preserved.
- **Icons** are first-class: `icon` layers reference a bundled open icon
  library by `(set, name)` + color/stroke props (rendered locally — no
  network), or a tenant-uploaded SVG that is **sanitized or rasterized on
  upload** (SVG can carry scripts — see §9).
- **Animation metadata** is part of the layer schema, not an afterthought:
  every layer may carry an `animation` block —
  `{ enter: {preset, duration_ms, delay_ms, easing}, exit: {...},
  emphasis: {...} }` — and every page a `transition` preset. Presets are a
  **closed validated set** (`fade, slide_up/down/left/right, pop,
  typewriter, ken_burns, wipe`…), which keeps rendering deterministic and
  the renderer secure. Static exports ignore animation; video/reel renders
  apply it (animated text overlays, logo stings, page transitions) —
  this is what makes one design model serve both a poster and a reel.
- **Brand tokens, not hardcoded values**: `"brand:primary"`,
  `"font_family": "brand:heading"` resolve against the active `brand_kit`
  at render time. Re-skinning a design to another brand = swap the kit.
- **Asset references are storage keys or `source_kind/source_id` pointers**
  — never URLs. Every referenced key/id is validated as tenant-owned on
  save and on render (cross-tenant reference = rejected).
- **Text is real text** (a text layer), never baked into a generated image
  — that's what makes AI posters editable. The image model generates
  *backgrounds/subjects*; headlines/CTAs/logos are layers on top.

### 1.2 Versioning — `creative_design_revision` (the collaboration backbone)

Every mutation (AI generate, AI edit, **human edit**) appends an immutable
revision snapshot — there is **no in-place mutation of a design**. This is
the platform's **Human+AI Collaboration Invariant**
(`HUMAN_AI_COLLABORATION_INVARIANT.md`): AI Mode / Guided Mode / Pro Mode
are three *actors* writing to the same `creative_design` through one write
path (`apply_revision`), not three code paths.

`creative_design_revision` carries:
`(design_id, revision_n, doc, ops, source, parent_revision_id, actor_kind,
mode, created_by_user_id, review_status, edit_summary, created_at)`.
`source ∈ {ai_generate, ai_edit, ai_regenerate, ai_restyle, ai_transform,
user_edit, template}`. `creative_design` holds `head_revision_id` +
`current_revision` (optimistic lock — a stale base → 409, the editor
rebases) and `doc` as a denormalized cache of the head.

This one append-only, parent-linked log directly provides **undo/redo,
version history, branching, A/B (a variant = a branch), approval workflows
(`review_status` + RBAC), and team collaboration** — see the invariant doc
§2. Housekeeping caps retained linear revisions per design via a periodic
job (branches/approved revisions retained). Real-time multi-cursor
collaboration (CRDT/websockets) remains a later phase; optimistic locking
+ branching covers asynchronous team editing now.

---

## 2. Schema impact (all additive — the V0 bet pays off)

| Table | Change |
|---|---|
| **`creative_design`** | **NEW** — tenant FK, `creative_project_id` FK, name, `media_type`, `doc` JSONB (head cache), `current_revision`, `head_revision_id`, `default_mode` (`ai\|guided\|pro` — UI default only), status |
| **`creative_design_revision`** | **NEW** — design FK, `revision_n`, `parent_revision_id` (self-FK → branching), `doc` JSONB, `ops` JSONB (the diff), `source` (`ai_generate\|ai_edit\|ai_regenerate\|ai_restyle\|ai_transform\|user_edit\|template`), `actor_kind` (`ai\|human`), `mode`, `review_status` (`draft\|pending\|approved\|changes_requested`), `created_by_user_id`, `reviewed_by_user_id`, `edit_summary`. **Immutable / append-only** — the single write path is `apply_revision`. |
| **`brand_asset`** | **NEW** — the brand-kit file library: `brand_kit_id` FK, `kind` (`logo\|font\|image\|audio\|color_palette`), storage ref, `name`, metadata (e.g. font family/weights). Multiple logos/fonts per kit — the single `logo_storage_key` column stays for back-compat as "primary logo." |
| `creative_asset` | ADD `design_id` + `design_revision` — an asset is a render of a specific revision. **Required for every studio-generated creative** (Editability Invariant §0.1); nullable only for legacy V0 rows + raw uploads. Plus `source_kind='upload'` joins the enum: **user uploads become library rows too** — one Asset Library for generated, rendered, and uploaded media. |
| `creative_template` | No schema change. `spec` JSONB now holds: a design document + `placeholders` (named slots: `{{headline}}`, `{{logo}}`, `{{product_image}}`, `{{cta}}`) + default brand-token bindings. Instantiating a template = copy doc, fill placeholders (AI or user), resolve brand tokens → new `creative_design`. |
| `creative_format` | No change — already drives canvas dimensions + auto-resize targets. |
| `creative_export` | No change — already models (asset → target format → storage ref). The resize/export engine fills it. |
| `creative_project` / `creative_variant` / `creative_cost_event` | No change. Variants now point at assets rendered from *forked designs* (fork = copy doc → new design → tweak one variable) — strictly better A/B. |
| RLS | the 2 new tenant tables (`creative_design`, `creative_design_revision`, `brand_asset`) join `RLS_TABLES` + get dormant policies. |
| Metering | usage kinds += **`ai_edit`** (NL edit = an LLM call) and **`export`** (tracked, default unlimited); existing `generation` covers studio image creatives; video keeps `video_generation`/`video_second`. All quotas stay DB-configurable in `plan_quota`. |

**No renames, no breaking changes, no data migration** — exactly the
outcome the early `creative_*` naming was chosen to enable.

---

## 3. AI generation becomes design composition

Each creative type gets a **composer** that emits a `creative_design`, not
a flat file. Composers share one pattern:

```
brief + brand_kit + creative_format + (optional template)
   │
   ├─ copy layer:    LLM (existing content engine) → headline/body/CTA text
   ├─ visual layer:  image provider (existing visuals engine) → background/subject
   ├─ brand layers:  logo (brand_asset), colors/fonts as brand tokens
   └─ layout:        template slots OR an LLM-chosen layout from a curated set
   ▼
creative_design (revision 1, source='ai_generate') → render → creative_asset
```

| Creative type | Pages | Notable layers |
|---|---|---|
| Poster / Banner / Thumbnail / Reel cover | 1 | bg image, headline text, CTA, logo |
| Carousel | N (one per slide) | per-slide image + text; shared brand frame |
| Social post | 1 | image + caption text layer (+ the caption *copy* still lands in `generated_content` for the content studio — both register the same `creative_asset`) |
| Video ad / Reel (Veo) | N (one per scene) | **video layer** (Veo clip via `video_render`), text overlays, audio layer (TTS), end-card page |

**Layout quality control:** the LLM does not freestyle pixel coordinates.
It selects + parameterizes from a **curated layout library** (code-defined
layout functions / template slots), which is how Canva templates stay
professional. Free-form layout generation can be added later behind the
same composer interface.

**Existing `visuals`/`content` modules remain untouched** (constitution:
no rewrites). The studio composers *reuse* their engines (image provider,
copy prompts) as services. Migration of those studios' UIs onto designs is
a later, optional consolidation.

---

## 4. Veo 3 video — integrated, not standalone (upgrade of the V0 pipeline)

The V0 stub pipeline wrote a flat asset. The studio version changes the
pipeline's **output shape** — same jobs, same providers, same tenancy:

```
script → storyboard → creative_design (pages=scenes; layers=placeholder)
       → per-scene Veo render (video_render) → fills each page's video layer
       → TTS (TTSProvider)                   → audio layers
       → subtitles                            → text layers (timed)
       → brand kit                            → logo bug / end-card page / colors
       ▼
the design IS the editable timeline  ──render(ffmpeg)──▶ creative_asset (mp4)
```

So a generated reel is **editable like everything else**: swap a scene's
clip, rewrite an overlay, change the end-card CTA, re-render. The
"timeline editor" in the frontend is just the layer editor with a
time axis on pages. Veo, TTS, storage, cost, metering — all unchanged
from the approved V0/V1 design. This is the integration the requirement
asks for: video is a *media type inside the studio*, not a parallel app.

---

## 5. AI Editing — natural language → validated edit operations

The Jasper-style copilot, made safe by the closed layer schema:

```
"make the headline bigger, move the logo top-right, change background to navy"
   │
   ▼  LLM (existing router) receives: design doc + brand kit + instruction
   ▼  returns STRUCTURED EditOps (Pydantic-validated) — never a whole document:
   [ {op:"update_layer", layer_id:"ly_2", set:{"props.font_size": 96}},
     {op:"move_layer",   layer_id:"ly_logo", set:{"x": 880, "y": 40}},
     {op:"update_layer", layer_id:"ly_1", set:{"props.fill": "#0B1F3A"}} ]
   ▼
server applies ops → new creative_design_revision (source='ai_edit',
edit_summary=instruction) → preview render → user keeps or undoes (revert
to previous revision)
```

Why ops, not documents: token cost, no drift/corruption of untouched
layers, auditable diffs, trivially undoable, and the op whitelist
(`add_layer / update_layer / move_layer / delete_layer / reorder /
add_page / apply_brand_token`) is a security boundary — the model cannot
introduce anything outside the validated schema. Instructions pass through
the existing prompt sanitizer; each edit is metered (`ai_edit`) and
cost-tracked (`creative_cost_event stage='ai_edit'`).

### 5.1 Section regeneration ("regenerate just this part")

Distinct from a text edit: the user targets a **layer or a `role`** and
asks for a *new generation* of it, keeping everything else. This is where
the layer model + semantic roles pay off — only the targeted slot is
re-invoked, the rest of the design is untouched.

```
POST /creative/designs/{id}/regenerate
   { target: "layer:ly_bg" | "role:background" | "role:headline" | "page:pg_2",
     instruction?: "warmer, more premium" }
   │
   ▼ route by the target layer's type/role to the right engine:
     • image / role=background|product → image provider (new background/subject)
     • text  / role=headline|cta|body  → copy engine (new line, brand voice)
     • video / a scene page            → video subsystem (re-render that scene only)
     • icon / shape                    → swap from library / recolor
   ▼ produce N candidates → replace ONLY the targeted layer(s) in a COPY of
     the doc → new creative_design_revision (source='ai_regenerate') → preview
   ▼ user keeps the candidate they like (or reverts) — a "shuffle" UX
```

Because regeneration writes the same layer slot (same id, role, geometry,
animation), the new content drops into the existing composition without
disturbing layout — that's the Canva/Pomelo "regenerate this image" feel.
Metered as `generation` (image/text) or `video_generation` (scene), cost
tracked in the ledger, audited like any generation. The whole-design
"regenerate" is just every-role regeneration in one call.

---

## 6. Rendering + multi-format export engine

### 6.1 `DesignRenderer` abstraction (same pattern as every provider)
```
render(design_doc, brand_kit, *, page=None, format) -> bytes
```
**Recommended implementation: HTML/CSS → headless Chromium (Playwright)
in the worker image**, paired with a **DOM-based frontend editor**. The
decisive argument: editor preview and server render use the *same
rendering technology*, so WYSIWYG parity is structural, not aspirational
(this is the hardest problem in editor products). Static media renders a
page to PNG/JPEG/PDF; video renders overlay frames that ffmpeg composites
with the video/audio layers. A `StubRenderer` backs tests (no Chromium in
CI), exactly like the provider stubs.

### 6.2 Multi-format export + automatic resizing (Adobe-Express-style)
`POST /creative/designs/{id}/export {format_slugs:[...]}` fans out Arq
jobs: for each target `creative_format`, an **auto-layout pass** adapts
the design (canvas resize; layers repositioned via per-layer anchor
constraints + the format's `safe_zones` from the brand kit; font scaling
rules), renders, stores, writes a `creative_export` row. One design →
Instagram 9:16 + Meta 4:5 + banner 16:9 in one click. Constraint
metadata (`anchor`, `scale_mode`) is part of the layer schema so
templates resize predictably.

---

## 7. Template, Brand Kit, Asset Library architectures (filled in)

**Templates** (`creative_template`, no schema change) — **GENERATED, never
categorized** (No-Template-Categories invariant, `OUTCOME_TO_CREATIVE_SYSTEM.md`
§3.2). A template is a design doc with named placeholders + brand-token
bindings, but the system has **no industry-tagged catalog** ("restaurant
templates" etc. are forbidden). Sources: (a) **dynamically generated** by
the composer from design primitives + layout systems + brand tokens +
objective composition rules (§4 of the outcome doc) — parameterized by
objective/audience/brand/platform, never by industry; (b) "save my design
as a template" (a tenant-owned cache of a good generated output); (c) a
small set of **objective-shaped layout primitives** that are
industry-free (e.g. "single-CTA lead layout", "social-proof event layout")
— selected by outcome semantics, not industry. Instantiation = copy → AI
fills placeholder copy from the brief → resolve brand tokens → new design.
There is **no `industry` column** on `creative_template` (or formats, or
the objective taxonomy).

**Brand Kit** (`brand_kit` + new `brand_asset`): multiple logos, uploaded
fonts (TTF/WOFF2 → validated, stored, loaded by the renderer; licensing is
the customer's responsibility — surfaced in UI copy), color palettes,
brand voice (`voice_provider`/`voice_id` for TTS — already there), audio
ident, safe zones. Brand tokens (§1.1) are the binding mechanism that
makes every design re-brandable. Brand-kit application to video (logo
bug, end card) already designed in V0 — unchanged.

**Asset Library** (`creative_asset` — already the unification point):
now also ingests **uploads** (`source_kind='upload'`; file-type allowlist,
size caps, image sanitization) so founders can use their own photos/clips
as design layers. The `/library` UI gets one cross-media grid: generated,
rendered, uploaded — filterable by media/creative type, searchable
(pgvector semantic search slots in here later, per the roadmap).

---

## 8. APIs (added to the existing `/api/v1/creative/*`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/creative/designs` | create (blank, from template, or from brief → AI compose) |
| GET | `/creative/designs/{id}` | doc + revision head |
| PUT | `/creative/designs/{id}` | save user edit (optimistic-lock on revision) → new revision |
| POST | `/creative/designs/{id}/ai-edit` | NL instruction → EditOps → new revision |
| GET | `/creative/designs/{id}/revisions` | history |
| POST | `/creative/designs/{id}/revert` | revert to revision N |
| POST | `/creative/designs/{id}/render` | render current revision → creative_asset |
| POST | `/creative/designs/{id}/export` | multi-format export fan-out |
| POST | `/creative/designs/{id}/fork` | duplicate (variant / re-brand base) |
| CRUD | `/creative/templates` | tenant templates + built-ins |
| CRUD | `/creative/brand-kits`, `/creative/brand-assets` (+ upload) | brand kit mgmt |
| POST | `/creative/uploads` | library upload (multipart; validated) |

All tenant + `video.create`-family permission-gated (slugs may generalize
to `creative.*` aliases later — additive). Existing project/start/cost
endpoints unchanged. Render/export/AI-edit run as Arq tenant jobs
(long-running ops stay async — standing rule).

---

## 9. Security, tenancy, metering (deltas only — everything else inherited)

- **Renderer is a security boundary**: design content is *data*. Text is
  escaped; only schema-validated style props reach CSS; **no raw HTML/CSS/
  JS anywhere in a design**; Chromium runs sandboxed in the worker with no
  network (assets pre-fetched from storage to local tmp) → kills XSS-in-
  render and SSRF classes outright.
- **Cross-tenant reference check**: every `storage_key` / `source_id` in a
  saved or rendered design must resolve to a row/key owned by the design's
  org. Enforced on save AND render (defense in depth with RLS).
- **Uploads**: extension+MIME allowlist, size caps, image re-encode
  (strips EXIF/active content), fonts parsed/validated before acceptance.
- **AI edit**: instruction → prompt sanitizer; output → strict EditOps
  schema; op count + size caps per request.
- **Metering/cost**: `ai_edit` usage kind (quota-able per plan, DB rows);
  renders/exports cost-tracked in `creative_cost_event`
  (`stage='render'|'export'`, compute-time units); existing video +
  generation metering unchanged. Org budget cap covers the new stages
  automatically (same ledger).
- **Audit**: every AI generate/edit lands in `ai_audit_events` (action
  `generate_creative` / new `edit_creative`), no content stored — as ever.

---

## 10. Phased delivery (each ships independently, dark where new)

| Phase | Scope | Builds on |
|---|---|---|
| **CS1 — Design model** | `creative_design` + revisions + `brand_asset` (migration, RLS, models), Pydantic layer schema, design CRUD + fork/revert APIs, tenant-ownership validation, V0 video pipeline emits designs | shipped V0 |
| **CS2 — Render + export** | `DesignRenderer` (stub + Chromium impl), render job, multi-format export + auto-resize, ffmpeg video render of design timelines | CS1, V1 video |
| **CS3 — AI composers** | poster/banner/thumbnail/social-post/carousel composers (reuse image+copy engines, curated layouts, brand tokens), templates seeded | CS1–2 |
| **CS4 — AI editing** | NL → EditOps → revision, metering (`ai_edit`), preview loop | CS1–3 |
| **CS5 — Editor frontend** | DOM-based canvas editor: viewer → property panel → full manipulation; library grid; brand-kit UI | CS1–4 |
| **CS6 — Studio polish** | template marketplace, video timeline UI, semantic search (pgvector), collaboration (future) | CS5 |

CS1 is the keystone and is small (schema + validation + CRUD — the same
shape as every prior foundation phase). The frontend editor (CS5) is the
single largest item and is deliberately last — every API beneath it will
already be real and tested.

---

## 11. Open decisions (need your call before CS1 build)

1. **Renderer tech** — headless Chromium/Playwright in the worker
   (recommended: WYSIWYG parity with a DOM editor) vs Skia/Pillow
   (lighter image, weaker text/layout fidelity, no parity).
2. **Editor canvas tech** — DOM-based (recommended, pairs with #1) vs
   canvas libs (konva/fabric).
3. **Built-in template ownership** — system org vs `is_system` flag on
   `creative_template` (recommend: nullable-tenant + `is_system`, mirrors
   the global-roles pattern).
4. **`ai_edit` default quotas** per plan (DB rows; placeholders fine).
5. **Stock assets** — out of scope for now, or reserve an
   `source_kind='stock'` + provider seam? (Recommend: reserve the enum
   value only; integrate later.)

---

## 12. Constraint adherence
PostgreSQL remains the system of record (designs, revisions, templates,
brand data, costs, quotas, audit — all PG; only bytes in storage) · all
new tables `TenantMixin` + RLS-registered · everything metered + budget-
capped · additive migrations only · no rewrites of `visuals`/`content` ·
Veo integrated as a studio media type, not a standalone module · every
abstraction (renderer, composer, providers, storage) reusable across all
current and future creative types.
