# CS1 — Creative Studio Foundation — Technical Design (GATE)

> The six-section gate that precedes CS1 implementation. This is a **build
> spec**, not architecture expansion — it commits the already-approved
> design (`CREATIVE_STUDIO_ARCHITECTURE.md`, `OUTCOME_TO_CREATIVE_SYSTEM.md`,
> `HUMAN_AI_COLLABORATION_INVARIANT.md`) to concrete tables, modules,
> endpoints, and slices. Governed by the **Creative Studio Constitution**
> (CLAUDE.md). Alembic head at design time: `0034_creative_core`.
> Date: 2026-06-15.

## Scope (the seven subsystems, this phase only)

| Subsystem | CS1 deliverable | Deferred to |
|---|---|---|
| **1. Design Model** | `creative_design`, `creative_design_revision`, `brand_asset`, `growth_objective`, `objective_kind`, `layout_primitive` tables + ORM + schemas | — |
| **2. Revision Engine** | `apply_revision` single write path + optimistic lock + immutability guard | branching/approval UI → CS5 |
| **3. Editable Layer System** | closed layer-doc Pydantic schema (validate every revision) + EditOp grammar | live canvas editor → CS5 |
| **4. Transform Engine** | `transform`/`restyle` **endpoints + dispatch contract** (stub composers) | real composition → CS3 |
| **5. AI Edit Router** | NL→{edit·regenerate·transform·restyle·variant} **classifier interface** (stub) | real LLM ops → CS4 |
| **6. Studio APIs** | full flag-gated router surface (`/api/v1/creative/designs/*`) wired to the engine | — |
| **7. Studio UI Foundation** | read-only design viewer + revision history panel behind `NEXT_PUBLIC_STUDIO_ENABLED` | editing UI → CS5 |

CS1 ships **dark** (flag-gated, default off). It builds the *spine* — the
design object, the one write path, validation, and the API/UI shell — so
CS3/CS4/CS5 only add composers + ops + canvas, never new plumbing.

---

## 1. Technical design

### 1.1 Module layout (additive — no rewrites)

```
modules/creative/                      (extend existing)
  design/
    models.py        creative_design, creative_design_revision, brand_asset
    schemas.py       LayerDoc, Layer (closed union), EditOp grammar, requests
    layer_schema.py  the CLOSED validator (no raw HTML; tenant-owned refs)
    revision.py      apply_revision()  ← THE ONLY WRITE PATH
    router.py        /api/v1/creative/designs/*  (flag-gated)
    transform.py     transform/restyle dispatch (stub composers in CS1)
    ai_router.py     NL → op-class classifier interface (stub in CS1)
  layout/
    primitives.py    layout_primitive registry stub (Law 2 — generated, not categorized)
modules/growth/                        (NEW package)
  models.py          growth_objective, objective_kind
  catalog.py         objective_kind seed (outcome semantics, industry-FREE)
  schemas.py
  router.py          /api/v1/growth/objectives/*
```

`apply_revision` lives in `modules/creative/design/revision.py` and is
imported by the router, transform, ai_router — **every** writer. No other
function may assign `creative_design.doc`.

### 1.2 Design Model (the source object)

- `creative_design` — the editable document head. Holds `doc` (JSONB layer
  document, a denormalized cache of the head revision), `current_revision`
  (int, optimistic lock), `head_revision_id`, `default_mode`, tenancy,
  links to `creative_project` + `growth_objective`.
- `creative_design_revision` — **immutable, append-only** snapshot per
  change: `revision_n`, `parent_revision_id` (self-FK → branch tree),
  `doc`, `ops` (the diff), `source`, `actor_kind`, `mode`, `review_status`,
  `created_by_user_id`, `reviewed_by_user_id`, `edit_summary`.
- `brand_asset` — tenant-owned uploaded assets (logo/font/image/color) the
  layer doc references by id (`brand:logo`, asset refs). Replaces ad-hoc
  storage keys with a first-class, tenant-scoped, RLS'd table.

### 1.3 Editable Layer System (the closed document schema)

`LayerDoc` (Pydantic, the **only** accepted shape — validated on every
revision):

```
LayerDoc:
  version: int
  format_slug: str            # → creative_format (size/aspect)
  pages: list[Page]           # 1 for static, N for carousel, scenes for video
Page:
  background: Background
  layers: list[Layer]         # ordered = z-order
  duration_ms: int | None     # video/animation
Layer = TextLayer | ImageLayer | IconLayer | ShapeLayer | VideoLayer
      | AudioLayer | GroupLayer        # CLOSED union — no "html"/"raw" type
  common: id, role, x, y, w, h, rotation, opacity, z, animation?, locked?
  role ∈ {background, logo, headline, subhead, body, cta, product,
          decoration, subtitle}        # semantic, industry-FREE
  brand-bound props accept tokens: color="brand:primary", font="brand:heading"
```

**Validation gates (every revision, every mode):** closed type union (no
raw HTML / script), every asset ref resolves to a `brand_asset`/
`creative_asset` **owned by the same org**, every `brand:*` token resolves
in the active `brand_kit`, geometry within format bounds. A human in Pro
Mode and the AI in Guided Mode pass through the *same* validator — Law 3.

**EditOp grammar** (the diff vocabulary both AI and the future canvas emit):
`add_layer · update_layer · move_layer · resize_layer · delete_layer ·
reorder · add_page · delete_page · apply_brand_token · set_animation ·
set_background · set_text`. Each op is a small validated Pydantic model;
`apply_ops(doc, ops) -> doc` is pure.

### 1.4 Revision Engine (the one write path)

```python
async def apply_revision(
    session, *, design, actor_kind, mode, source, base_revision,
    ops=None, full_doc=None, created_by_user_id=None, edit_summary=None,
) -> CreativeDesignRevision:
    # 1. optimistic lock
    if base_revision != design.current_revision: raise StaleRevision  # → 409
    # 2. next doc
    next_doc = apply_ops(design.doc, ops) if ops is not None else full_doc
    # 3. VALIDATE against the closed layer schema (raises 422 on violation)
    validated = LayerDoc.model_validate(next_doc); assert_tenant_refs(validated, org_id)
    # 4. INSERT immutable revision (parent = current head)
    rev = CreativeDesignRevision(design_id=…, revision_n=design.current_revision+1,
            parent_revision_id=design.head_revision_id, doc=validated.model_dump(),
            ops=dump(ops), source=source, actor_kind=actor_kind, mode=mode,
            created_by_user_id=created_by_user_id, review_status="draft", …)
    session.add(rev); await session.flush()
    # 5. advance head (the only mutation of creative_design.doc, in this fn)
    design.head_revision_id = rev.id; design.doc = rev.doc
    design.current_revision = rev.revision_n
    # 6. same TX: audit (ai_audit_events for ai_*; row itself for user_edit) + meter
    return rev
```

Immutability is enforced structurally (no UPDATE/DELETE path on the
revision table in app code) and, once RLS least-priv lands, at the grant
level. A review/lint guard forbids `.doc =` assignments outside this file.

### 1.5 Transform Engine + AI Edit Router (interfaces now, composers later)

- **Transform** (`transform.py`): `reformat · recompose · remediate` +
  `restyle` each map to a function that, in CS1, produces a *deterministic
  stub design* (clone + format/style metadata change) through
  `apply_revision`/new-design — proving the **contract + metering + audit +
  preserve-source** path. CS3 swaps the stub body for real composers; the
  signature and the route do not change.
- **AI Edit Router** (`ai_router.py`): `classify(instruction) ->
  {edit·regenerate·transform·restyle·variant}` returns a stub classification
  in CS1 (rule-based) behind the same interface the CS4 LLM classifier will
  implement. The dispatch table that turns a class into an `apply_revision`
  call is real now.

This is deliberate: CS1 freezes every **boundary** (write path, schema,
routes, metering, audit) so later phases are pure fill-in, never replumb.

---

## 2. DB impact

**One additive migration: `0035_creative_studio` (down_revision `0034_creative_core`).**

| Table | Kind | Key columns |
|---|---|---|
| `objective_kind` | NEW catalog (non-tenant, RLS-excluded like `creative_format`) | `slug` PK, `display_name`, `category` (lead/sale/booking/awareness/retention/traffic/install/hire/signup), `kpi_hint`, `default_channels` JSONB, `is_active`, `sort_order` |
| `growth_objective` | NEW tenant table (RLS) | `id`, tenancy, `objective_kind` FK, `statement` (free text), `audience_hypothesis`, `budget_cents?`, `status`, `business_profile_id?` |
| `creative_design` | NEW tenant table (RLS) | `id`, tenancy, `creative_project_id` FK, `growth_objective_id?` FK, `format_slug?` FK, `name`, `media_type`, `doc` JSONB, `current_revision` int, `head_revision_id?`, `default_mode`, `status` |
| `creative_design_revision` | NEW tenant table (RLS, **append-only**) | `id`, tenancy, `design_id` FK, `revision_n`, `parent_revision_id?` self-FK, `doc` JSONB, `ops` JSONB?, `source`, `actor_kind`, `mode`, `review_status`, `created_by_user_id?`, `reviewed_by_user_id?`, `edit_summary?`, `created_at` |
| `brand_asset` | NEW tenant table (RLS) | `id`, tenancy, `kind` (logo/font/image/color/icon), `storage_backend`, `storage_key`, `mime_type?`, `meta` JSONB, `label?` |
| `layout_primitive` | NEW catalog (non-tenant, RLS-excluded) | `slug` PK, `kind` (grid/hierarchy/focal/type_scale/color_system), `params` JSONB, `objective_affinity` JSONB (outcome semantics — **no industry**), `is_active` |
| `campaign_plans` | ALTER (additive) | add `objective_id` UUID FK → `growth_objective` (nullable; back-compat) |

**Indexes:** `(organization_id, brand_id)` on each tenant table;
`(design_id, revision_n)` unique on revisions; `(growth_objective_id)` on
designs; partial index `WHERE status='active'` on objectives.

**RLS:** add the 4 new tenant tables (`growth_objective`, `creative_design`,
`creative_design_revision`, `brand_asset`) to `ORG_SCOPED_TABLES` in
`db/rls.py` and emit dormant policies in the migration (same pattern as
0034). Catalogs (`objective_kind`, `layout_primitive`) excluded, like
`creative_format`/`plan`. Policies stay dormant (flag off) — no behavior
change.

**Seeds (industry-FREE — Law 2):** `objective_kind` rows keyed on *outcome*
(get_leads, get_bookings, drive_sales, grow_awareness, drive_installs,
hire, get_signups, drive_traffic, retain_customers); `layout_primitive`
rows keyed on composition (single_focal_grid, credibility_stack,
social_proof_band, strong_offer_hero, type_scale_editorial, …). **Zero
industry strings in any seed or control flow** — verified by the CI guard
(§4).

**No data backfill.** `campaign_plans.objective_id` is nullable; existing
rows keep working. No existing creative/video table is altered.

---

## 3. APIs

All under `/api/v1`, all `Depends(require_permission(...))`, all
**flag-gated** (`STUDIO_ENABLED`, default off → 409 like the existing
creative router). Every write funnels through `apply_revision`.

| Method · Path | Perm | Mode | Effect |
|---|---|---|---|
| `POST /growth/objectives` | `growth.create` | — | create `growth_objective` from NL goal + objective_kind |
| `GET /growth/objectives` · `/{id}` | `growth.read` | — | list / read |
| `GET /growth/objective-kinds` | `growth.read` | — | catalog (for intake UI) |
| `POST /creative/designs` | `content.create` | AI | new design → revision 1 (`ai_generate`, stub composer in CS1) |
| `GET /creative/designs` · `/{id}` | `content.read` | — | list / read head doc |
| `POST /creative/designs/{id}/ai-edit` | `content.create` | Guided | NL → ops → revision (`ai_edit`) |
| `POST /creative/designs/{id}/regenerate` | `content.create` | Guided | section regenerate → revision |
| `POST /creative/designs/{id}/transform` | `content.create` | Guided | reformat/recompose/remediate → **new** design |
| `POST /creative/designs/{id}/restyle` | `content.create` | Guided | style-variant → new design/fork |
| `PUT /creative/designs/{id}` | `content.create` | Pro | editor ops/doc → revision (`user_edit`) |
| `POST /creative/designs/{id}/revert` | `content.create` | any | new head → old doc (a revision, not a rewind) |
| `POST /creative/designs/{id}/branch` | `content.create` | any | fork at a revision |
| `GET /creative/designs/{id}/revisions` | `content.read` | — | history (linear/tree) |
| `POST /creative/designs/{id}/revisions/{n}/submit`·`/approve` | `content.publish` | any | `review_status` transition |
| `POST /creative/brand-assets` · `GET …` | `content.create`/`read` | — | upload/list tenant brand assets |

RBAC: reuse `content.*`; add `growth.create`/`growth.read` perms + grants
in the migration (same pattern 0034 used for `video.*`). All endpoints take
`mode`/`source` as parameters — **no per-mode routes** (Law 3).

---

## 4. Security

- **Tenant isolation:** every new tenant table carries `TenantMixin`
  (org+brand NOT NULL) + dormant RLS policy; services filter by
  `brand_id`/`organization_id`. Revisions inherit the design's tenancy; a
  revision can never reference another org's design/asset (validated in
  `assert_tenant_refs`).
- **Closed-schema validation on every revision** (AI *or* human) — no raw
  HTML/script layer type exists; asset refs must be org-owned; brand tokens
  must resolve. Neither a model nor a user can inject unsafe content via any
  mode.
- **Immutability + audit:** revisions are append-only; `ai_*` sources also
  write `ai_audit_events` (who/what/when, **no generated content stored**
  beyond the design itself, which is the asset). Human edits are audited by
  the revision row.
- **Approval gates publish:** publish/auto-publish requires the head
  revision `review_status='approved'` (or brand auto-approve) + the
  `content.publish` perm — same human-in-the-loop gate the autonomous loop
  needs.
- **Metering + cost caps:** AI revisions call `billing_live.enforce_quota`
  (pre) + `record_metered` (post) by source (`generation`/`ai_edit`/
  `video_generation`); transforms/restyles metered as generations. Org
  budget + daily caps inherited from the billing module.
- **No secrets / no card data / no vendor lock-in:** unchanged — the studio
  uses the existing provider abstractions + storage backends.
- **Law-2 CI guard:** a test greps `modules/creative`, `modules/growth`,
  and prompt files for industry literals and **fails** if any appear in
  control flow or seeds (allowed only inside prompt-context strings). Pins
  "no template categories" permanently.
- **Flag-gated dark launch:** `STUDIO_ENABLED=false` default → every route
  409s; UI hidden behind `NEXT_PUBLIC_STUDIO_ENABLED`. Zero production
  surface until explicitly turned on.

---

## 5. Rollback

- **Migration:** `0035_creative_studio` `downgrade()` drops the 6 new tables
  + the `campaign_plans.objective_id` column + the RLS policies + the
  `growth.*` perms/grants, returning to `0034`. Verified live
  (apply → downgrade → re-apply) before sign-off, per standing practice.
  Additive + nullable → downgrade is non-destructive to existing data.
- **Feature flags:** `STUDIO_ENABLED=false` (default) neutralizes the entire
  surface without a deploy; `NEXT_PUBLIC_STUDIO_ENABLED=false` hides the UI.
  RLS policies dormant (independent `DB_RLS_ENABLED` switch) — CS1 changes
  no isolation behavior.
- **Blast radius:** nothing existing imports the new modules; the only edit
  to a live path is the nullable `objective_id` FK on `campaign_plans`
  (back-compat). Reverting the flag fully disables CS1.

---

## 6. Success metrics

**CS1 is "done" (dark) when, with flags off, the app behaves identically,
and with flags on in a test:**

1. `0035` applies, downgrades, and re-applies cleanly (live evidence).
2. A design can be created (revision 1), AI-edited (revision 2), reverted
   (revision 3 → doc of 1), and branched — all via `apply_revision`; the
   revision chain + parent pointers are correct.
3. **No in-place mutation:** a test asserts `creative_design.doc` only ever
   changes through `apply_revision` (grep guard + behavioral test); a stale
   `base_revision` returns 409.
4. **Closed-schema validation** rejects a raw-HTML layer, a cross-org asset
   ref, and an unresolved brand token (422) — for both an AI op and a Pro
   `PUT`.
5. **One code path across modes:** the same `apply_revision` + validator run
   for `ai_generate`, `ai_edit`, and `user_edit` (asserted by test
   exercising all three).
6. **Law-2 guard** passes (no industry literals in control flow/seeds).
7. Tenant isolation + dormant RLS tests green; `pytest` + `pnpm
   typecheck/lint/build` clean.
8. With `STUDIO_ENABLED=false`, every studio route returns 409 and the UI is
   absent (no regression to existing surfaces).

KPI framing (Law 1): every `creative_design` is FK-traceable to a
`growth_objective`; the studio's north star is *objective KPI lift*, not
asset count — wired structurally now, measured in Phase C.

---

## Implementation slices (CS1 — verify each before the next)

| Slice | Deliverable | Verify |
|---|---|---|
| **CS1-1** | migration `0035_creative_studio` + RLS registration + seeds | apply/downgrade/re-apply live; `\d` tables |
| **CS1-2** | ORM models (`design/models.py`, `growth/models.py`) + env.py register | import + metadata resolves; isolated table create |
| **CS1-3** | layer schema + EditOp grammar + `apply_ops` (pure) | unit tests: validation rejects bad docs; ops apply |
| **CS1-4** | `apply_revision` engine + immutability/lock guards | tests: chain, 409, revert, branch, no-direct-mutation |
| **CS1-5** | growth module (catalog + service + router) | objective create/list; catalog seed present |
| **CS1-6** | creative design router + transform/restyle/ai-router stubs + metering/audit wiring | flag-gated 409; full flow with flag on; metered+audited |
| **CS1-7** | Law-2 CI guard + RBAC `growth.*` perms test | guard fails on planted literal; perms granted |
| **CS1-8** | Studio UI foundation (read-only viewer + revision history) behind `NEXT_PUBLIC_STUDIO_ENABLED` | `pnpm build`; viewer renders a design + history |
| **CS1-9** | full gate run + completion report | `pytest` + `pnpm` gates; report w/ rollback evidence |

CS1 builds the spine. CS3 adds composers (AI Mode real), CS4 the LLM op
router (Guided real), CS5 the canvas (Pro real) — each fills a frozen
boundary, none replumbs.
