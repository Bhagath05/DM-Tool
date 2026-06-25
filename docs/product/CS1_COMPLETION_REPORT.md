# CS1 — Creative Studio Foundation — Completion Report

> CS1 (the editable-design spine + outcome layer) is implemented and ships
> **dark** (flag-gated, default off). Governed by the Creative Studio
> Constitution (CLAUDE.md). Design gate: `CS1_TECHNICAL_DESIGN.md`.
> Date: 2026-06-15. Alembic head: `0035_creative_studio` (was `0034`).

## What shipped

| Subsystem | Where | State |
|---|---|---|
| **Design Model** | `0035_creative_studio` + `modules/creative/design/models.py` + `modules/growth/models.py` | ✅ 6 tables + `campaign_plans.objective_id` |
| **Editable Layer System** | `modules/creative/design/layer_schema.py` (closed `LayerDoc`) + `ops.py` (EditOps + `apply_ops`) | ✅ |
| **Revision Engine** | `modules/creative/design/revision.py` (`apply_revision` — the ONE write path) | ✅ |
| **Transform Engine** | `modules/creative/design/transform.py` (stub compose/transform/restyle) | ✅ contract frozen, composers → CS3 |
| **AI Edit Router** | `modules/creative/design/ai_router.py` (stub classifier) | ✅ interface frozen, LLM → CS4 |
| **Studio APIs** | `modules/creative/design/router.py` + `modules/growth/router.py` (flag-gated) | ✅ 15 endpoints |
| **Studio UI Foundation** | `apps/web` — `studio-config`, `studio-types`, `design-layout`, `DesignViewer`, `RevisionHistory`, `/studio` route | ✅ read-only, flag-gated |

Constitution laws made permanent in CLAUDE.md (LAW 1 Outcome-Driven, LAW 2
No Template Categories, LAW 3 Human+AI Collaboration). Canonical specs:
`OUTCOME_TO_CREATIVE_SYSTEM.md`, `CREATIVE_STUDIO_ARCHITECTURE.md`,
`HUMAN_AI_COLLABORATION_INVARIANT.md`.

## Success metrics → evidence (from the gate §6)

| # | Metric | Evidence |
|---|---|---|
| 1 | `0035` applies, downgrades, re-applies cleanly | **Live:** upgrade→`0035`, downgrade→all 6 tables dropped + `objective_id` removed + perms gone→`0034`, re-upgrade→`0035`. |
| 2 | create→edit→revert→branch via `apply_revision`; chain + parents correct | **Live:** chain `[1,2,3,4]` sources `[ai_generate, ai_edit, user_edit, user_edit]`, every `parent_revision_id` links to prior head. **Unit:** `test_revision_engine` (chain, parent pointers). |
| 3 | No in-place mutation; stale base → 409 | **Guard:** `test_law2_no_industry::test_no_direct_doc_mutation_outside_revision_engine` (grep: `.doc =` only in `revision.py`). **Behavioral:** `test_revision_engine::test_stale_base_revision_raises` (StaleRevision → router 409). |
| 4 | Closed-schema validation rejects raw-HTML / cross-org ref / unresolved token (AI *and* Pro) | `test_design_layer_schema` (html type, bad color, OOB geometry, cross-tenant) + `test_revision_engine` (invalid doc → no mutation; cross-tenant rejected) — same validator for `full_doc` and `ops`. |
| 5 | One code path across modes | `test_revision_engine::test_one_code_path_all_three_modes_same_function`; **Live:** ai_generate / ai_edit / user_edit all via `apply_revision`. |
| 6 | Law-2 guard passes (no industry literals in code/seeds) | `test_law2_no_industry` (AST scan of `modules/growth`, `modules/creative/design`, migration 0035 — clean; planted literal flagged). |
| 7 | Tenant isolation + dormant RLS green; `pytest` + `pnpm` clean | **Backend 982 passed**; RLS policies present on the 4 new tenant tables (dormant). **Frontend 585 passed**, `tsc --noEmit` clean, `next build` green. |
| 8 | `STUDIO_ENABLED=false` → routes 409, UI absent | `test_design_studio` (flag default → `_require_enabled` raises 409) + the `/studio` page renders a "coming soon" panel and makes **no** API calls while dark. |

KPI framing (LAW 1): every `creative_design` carries `growth_objective_id`
(FK) — the studio's north star is objective-KPI lift, wired structurally.

## Test inventory (new)

| Suite | Tests | Proves |
|---|---|---|
| `tests/creative/test_design_layer_schema.py` | 12 | closed schema rejects unsafe/invalid docs; tenant-ref enforcement |
| `tests/creative/test_design_ops.py` | 13 | EditOp grammar + pure `apply_ops`; result re-validates |
| `tests/creative/test_revision_engine.py` | 10 | one write path, chain/parents, 409 lock, revert, cross-tenant |
| `tests/creative/test_growth_module.py` | 6 | outcome catalog (industry-free), objective create/validate |
| `tests/creative/test_design_studio.py` | 13 | AI-router classifier, stub composer/transform, flag gate |
| `tests/creative/test_law2_no_industry.py` | 7 | Law-2 (no industry) + Law-3 (no direct doc mutation) + growth RBAC matrix |
| `apps/web` `design-layout.test.ts` / `studio-config.test.ts` | 11 | viewer render math + flag default-off |

## Decisions / deviations (intentional)

- **AI design actions metered as `generation`.** `usage_event.kind` has a
  CHECK constraint without an `ai_edit` value; rather than add a migration,
  CS1 meters generate/edit/transform/restyle against the existing
  `generation` quota and records the finer-grained source in the audit
  `action_type` (`design.ai_generate`, `design.ai_edit`, …). A dedicated
  `ai_edit` usage kind can be added later if per-edit quotas are wanted.
- **`/studio` is not in the sidebar nav while dark.** Correct for a
  dark-launched feature; CS5 adds navigation when the editor lands.
- **Cross-module references stay plain UUIDs** (no ORM FK to campaigns/
  growth/creative-core) — the established boundary rule; the DB keeps the
  real FKs from the migration.

## Rollback

- `alembic downgrade -1` drops the 6 tables + `objective_id` + RLS policies
  + `growth.*` perms (verified live, non-destructive — additive + nullable).
- `STUDIO_ENABLED=false` (default) + `NEXT_PUBLIC_STUDIO_ENABLED` unset
  neutralize the entire surface with no deploy. RLS dormant (independent
  `DB_RLS_ENABLED`). Blast radius: only the nullable `campaign_plans.objective_id`
  touches an existing table.

## Next (awaiting go-ahead)

CS1 froze every boundary (write path, schema, routes, metering, audit). The
remaining phases only fill them in — no replumbing:
- **CS3** — real composers (Strategy-driven dynamic template engine) → AI Mode real.
- **CS4** — LLM NL→ops classifier + transforms/restyles → Guided Mode real.
- **CS5** — interactive Pro-Mode canvas (same normalized coords + EditOps) + history/branch/approve UI.
