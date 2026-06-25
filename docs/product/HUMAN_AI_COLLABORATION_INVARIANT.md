# DM Tool — Human + AI Collaborative Creation (platform invariant)

> A core platform capability, not a future enhancement. Governs CS1+.
> Extends the Creative Studio + Outcome-to-Creative contracts.
> Architecture only — no code. Date: 2026-06-11.

## The keystone insight

**AI Mode, Guided Mode, and Pro Mode are not three features — they are
three *actors* writing to the same `creative_design` through one revision
pipeline.** A "mode" is just *who* is producing the next revision and *how
much* of the design they touch. There is exactly one design object, one
edit-op grammar, one revision log, one renderer. No mode has its own code
path, table, or storage.

```
                    ┌──────────────────────────────────────┐
   AI Mode  ───────▶│                                       │
   (AI creates)     │   ONE PIPELINE                        │
                    │                                       │     ┌──────────────────────┐
   Guided  ────────▶│   apply(EditOps | full doc) ──────────┼────▶│ creative_design_     │
   (AI modifies)    │   → validate → new revision           │     │ revision  (append)   │
                    │   → set creative_design.current_rev    │     └──────────┬───────────┘
   Pro Mode ───────▶│                                       │                │
   (human modifies) │                                       │                ▼
                    └──────────────────────────────────────┘     creative_design.doc
                                                                  (= revision head)
```

---

## 1. The two invariants (architecturally enforced)

### INV-1 — Single source object, no separate code paths
> AI Mode, Guided Mode, and Pro Mode all operate on the **same
> `creative_design`** via the **same** revision-producing service. There
> are no mode-specific tables, endpoints that bypass the design, or
> alternate storage. `mode` is metadata on the request, never a fork in
> the data model.

- **AI Mode = AI creates the design.** A composer produces revision 1
  (`source='ai_generate'`) from the objective/asset-plan — no human design
  work.
- **Guided Mode = AI modifies the design.** NL → EditOps / regenerate /
  restyle / transform → a new revision (`source='ai_edit' | 'ai_regenerate'
  | 'ai_restyle' | 'ai_transform'`).
- **Pro Mode = human modifies the design.** The layer/timeline/animation
  editor emits the **same EditOps** (or a full validated doc) → a new
  revision (`source='user_edit'`).

The Pro-mode editor and the AI both speak the **same EditOp grammar**
(`add_layer / update_layer / move_layer / delete_layer / reorder /
add_page / apply_brand_token / set_animation …`). A human dragging a layer
and the AI "move the logo top-right" produce *identical* ops. That is what
guarantees one code path: the apply-and-revise service neither knows nor
cares whether the ops came from a person or a model.

### INV-2 — Every action returns a revision; nothing mutates in place
> **No code may mutate `creative_design.doc` directly.** Every change —
> AI or human, full generation or one-pixel nudge — goes through
> `apply_revision(design, ops_or_doc, *, source, actor)`, which appends an
> immutable `creative_design_revision` and atomically advances
> `current_revision`. There is no UPDATE path to the live doc that skips
> the revision log.

Enforcement (structural):
- The service exposes **only** `apply_revision(...)` as the write path;
  `creative_design.doc` has no public setter. (A review/lint guard:
  assignments to `.doc` outside `apply_revision` are forbidden.)
- `apply_revision` is **transactional + optimistic-locked**: it takes the
  expected `base_revision`; a stale base → 409, the caller rebases. Two
  concurrent editors can't silently clobber each other.
- Revisions are **immutable + append-only** (no UPDATE/DELETE on
  `creative_design_revision`; at the DB grant level once RLS/least-priv is
  active). History is therefore tamper-evident.

---

## 2. What the revision log unlocks (all from one mechanism)

Because *every* change is a revision, these are not separate features —
they fall out of the log for free:

| Capability | How the revision model provides it |
|---|---|
| **Undo / redo** | move `current_revision` back/forward along the chain |
| **Version history** | list revisions (source, actor, summary, timestamp) |
| **Branching** | `parent_revision_id` (a revision may fork → a tree, not just a line) → "create another version" without losing the original |
| **A/B testing** | a branch rendered to an asset + linked to a `creative_variant`; variants are branches of one design |
| **Approval workflows** | a revision gains a `review_status` (draft→pending→approved/changes_requested); publish requires an approved revision |
| **Team collaboration** | `created_by_user_id` + roles on every revision → who changed what; brand approver gates publish (RBAC already exists) |

So the requirement "this enables undo/redo/history/branching/A-B/approval/
collaboration" is satisfied by **one** design decision (append-only
revisions with a parent pointer), not seven subsystems.

---

## 3. Schema delta (additive — on top of CS1's `creative_design_revision`)

The CS1 design already creates `creative_design` + `creative_design_revision`.
This invariant adds a few columns to make branching + approval + actor
first-class (still one additive migration, no renames):

`creative_design_revision` gains:
- `parent_revision_id` (self-FK, nullable) — enables a **revision tree**
  (branching), not just a linear chain.
- `source` already planned — extend the enum:
  `ai_generate | ai_edit | ai_regenerate | ai_restyle | ai_transform |
   user_edit | template`.
- `actor_kind` (`ai | human`) + `created_by_user_id` (nullable for AI) +
  `mode` (`ai | guided | pro`) — provenance for audit + collaboration.
- `review_status` (`draft | pending | approved | changes_requested`,
  default `draft`) + `reviewed_by_user_id` — approval workflow.
- `ops` JSONB (nullable) — the EditOps that produced this revision (a diff;
  the full `doc` snapshot is also stored for fast head reads + integrity).

`creative_design` gains:
- `head_revision_id` (FK) — the current head (what `doc` mirrors); `doc`
  stays as a denormalized cache of the head for fast reads.
- `default_mode` (`ai | guided | pro`, default `ai`) — the surface a
  brand/user lands in; **not** a behavior switch, just a UI default.

No new tables. RLS unchanged (the revision table is already tenant-scoped
and RLS-registered in the studio design).

---

## 4. The single write path (one function, every actor)

```
apply_revision(
    session, *, design, actor_kind, mode, source,
    base_revision,                 # optimistic lock
    ops: list[EditOp] | None = None,   # diff (preferred)
    full_doc: dict | None = None,      # whole doc (composer / import)
    created_by_user_id=None,
) -> CreativeDesignRevision
   1. assert base_revision == design.current_revision  else 409
   2. resolve next doc:  ops → apply to head doc   OR   full_doc
   3. VALIDATE the resulting doc against the closed layer schema
      (no raw HTML, tenant-owned asset refs, valid brand tokens)
   4. INSERT creative_design_revision (immutable, parent=current head, ops, source, actor…)
   5. design.head_revision_id = new; design.doc = new.doc; design.current_revision += 1
   6. (same TX) audit + meter the action by source/mode
```

Every entry point routes here:
- **Composer (AI Mode):** calls with `full_doc`, `source='ai_generate'`,
  `actor_kind='ai'`.
- **NL router (Guided Mode):** classifies instruction → `ops`,
  `source='ai_*'`, `actor_kind='ai'`.
- **Editor (Pro Mode):** sends `ops` (or doc), `source='user_edit'`,
  `actor_kind='human'`, `created_by_user_id=…`.

Three actors, one function. **This is the proof of "no separate code
paths."**

---

## 5. Endpoints (mode is a parameter, not a path)

The Studio APIs already defined gain a uniform shape — all funnel through
`apply_revision`:

| Endpoint | Mode | Produces |
|---|---|---|
| `POST /creative/designs` (from objective/plan) | AI | revision 1 (`ai_generate`) |
| `POST /creative/designs/{id}/ai-edit` | Guided | revision (`ai_edit`) |
| `POST /creative/designs/{id}/regenerate` · `/restyle` · `/transform` | Guided | revision (`ai_*`) |
| `PUT /creative/designs/{id}` (ops/doc from editor) | Pro | revision (`user_edit`) |
| `POST /creative/designs/{id}/revert` `{revision_n}` | any | new head pointing at an old doc (still a revision, never a destructive rewind) |
| `POST /creative/designs/{id}/branch` `{from_revision}` | any | a new branch head (parent set) |
| `POST /creative/designs/{id}/revisions/{n}/submit` · `/approve` | any | sets `review_status` (approval workflow) |
| `GET /creative/designs/{id}/revisions` | any | history (linear or tree) |

`revert` is itself a revision (you can undo an undo) — never a hard delete
of history.

---

## 6. Security, metering, audit (inherited, reinforced)

- **Approval gates publish:** a design can only be published/auto-published
  when its head revision is `approved` (or the brand allows auto-approve)
  — the same human-approval gate the autonomous loop requires, now backed
  by the revision's `review_status` + RBAC (`video.publish`/`content.publish`).
- **Every revision is audited** (`ai_audit_events` for AI sources; the
  revision row itself is the human-edit audit) — full who/what/when, no
  generated content stored beyond the design itself (which is the asset).
- **Every AI revision is metered + cost-tracked** by source
  (`ai_edit`/`generation`/`video_generation`) — already specified.
- **Validation on every revision** (closed schema, tenant-owned refs) means
  neither a human nor a model can introduce unsafe content via *any* mode.
- **Tenant isolation:** revisions inherit `creative_design`'s tenancy +
  RLS; a revision can never reference another tenant's design or assets.

---

## 7. Build alignment (folds into CS1 — not a new phase)

| Phase | Adds |
|---|---|
| **CS1 (amended again)** | `creative_design_revision` gets `parent_revision_id`, `actor_kind`, `mode`, `review_status`, `ops`; `creative_design` gets `head_revision_id`, `default_mode`. The **`apply_revision` single write path** + the "no direct `.doc` mutation" guard. (All additive; one migration with the design model.) |
| **CS3** | composers call `apply_revision(full_doc, source='ai_generate')` — AI Mode |
| **CS4** | NL router → ops → `apply_revision` — Guided Mode; + revert/branch/approve endpoints |
| **CS5** | Pro-mode editor emits the same ops → `apply_revision`; mode toggle is a UI default only; history/branch/approval UI |

**Modes are a UI lens over one engine.** A founder can start in AI Mode
(objective → everything), drop to Guided Mode ("make it premium"), and a
designer can open the same design in Pro Mode and nudge a layer — each
action is one more revision on the same object. Nothing is regenerated
from scratch, nothing is lost, every step is undoable and attributable.

---

## 8. Proposed CLAUDE.md addendum (one paragraph)

> **HUMAN+AI COLLABORATION INVARIANT.** Creative Studio has three modes —
> AI (AI creates), Guided (AI modifies), Pro (human modifies) — that all
> operate on the **same `creative_design`** through **one** revision
> pipeline. There are no mode-specific code paths or tables. **No code may
> mutate a design in place:** every change (AI or human) goes through
> `apply_revision`, which appends an immutable `creative_design_revision`
> and advances the head. This single mechanism provides undo/redo, version
> history, branching, A/B, approval workflows, and team collaboration. It
> is a core platform capability, present from CS1.
