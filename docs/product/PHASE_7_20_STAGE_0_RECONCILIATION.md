# Phase 7.20 · Stage 0 — Naming & Provenance Reconciliation

**Status:** Complete (documentation milestone). For review.
**Outputs:** [`BUSINESS_DNA_TERMINOLOGY.md`](./BUSINESS_DNA_TERMINOLOGY.md),
[`PROVENANCE_STANDARD.md`](./PROVENANCE_STANDARD.md), and this plan.
**Behaviour change:** none. No code, schema, migration, API, identifier, Ollama
routing, or runtime behaviour was modified. No commit/push/merge/deploy.

This stage establishes one vocabulary and one provenance standard so later stages
can converge the three composition layers **without** inventing a new system. It
changes documentation only; every correction below is *deferred and planned*.

---

## 1. Inconsistency inventory (verified against source)

Each item was confirmed by reading the code this stage, not assumed.

| # | Inconsistency | Evidence | Severity |
|---|---|---|---|
| **I1** | "Business Brain" names **two** different things: `advisor.brain.BusinessBrain` + `/advisor/brain` + `BusinessBrainResponse`/`BusinessBrainUpdate` (a **Business Profile projection**) vs. the `business_brain` module + `/business-brain` (the **Evidence/research store**). | `advisor/brain.py:11`, `advisor/schemas.py:163,175`, `advisor/router.py:176,197`; `business_brain/router.py:33`, `business_brain/models.py` | High |
| **I2** | Four surfaces informally called a "brain" (Business Brain, Marketing Brain, Brand Brain, advisor `BusinessBrain`) with no written distinction. | `marketing_brain/*`, `/brand-brain` UI, `advisor/brain.py` | High |
| **I3** | The `/brand-brain` UI page conflates **Brand Identity** (profile columns) with the **Business Brain evidence panel** (`/business-brain`) under one "Brand Brain" title. | `apps/web/src/app/(app)/brand-brain/page.tsx`, `.../_components/business-brain-panel.tsx` | Medium |
| **I4** | Four parallel provenance/confidence vocabularies, unreconciled: `BrainEvidence.kind`/`status`; belief `BeliefStatus`+derived confidence; `ContextProvenance` 5 tiers; Trust enums. | `business_brain/models.py`, `belief/enums.py`, `marketing_brain/provenance.py`, `trust/enums.py` | High |
| **I5** | Read-time freshness decay is applied to **Beliefs only**; `BrainEvidence` has `discovered_at` but is never decayed in composition. | `belief/freshness.py` vs `marketing_brain/service.py` | Medium |
| **I6** | Two competitor-research paths: evidence-grounded `business_brain` research vs. legacy `competitors` module (one-shot LLM, free-text `profile.competitors`, no persistence/grounding). | `business_brain/research_service.py` vs `competitors/service.py` | Medium |
| **I7** | Three composition services with divergent inputs (`GenerationContext` has brand identity + social, no evidence/beliefs; `MarketingBrainContext` has evidence, no beliefs/brand identity/social; `IntelligenceSignals` wraps MB + beliefs). | `context/builder.py`, `marketing_brain/service.py`, `advisor/signals.py` | High |
| **I8** | "DNA" is already used for **Creative DNA** (creative fingerprinting) in `performance`; "Business DNA" must stay distinct. | `performance/intelligence/creatives.py:9`, `performance/recommender.py:716` | Low (naming) |
| **I9** | Prompt/label drift: `render_context_block` labels the profile block "Business context" / "Brand Brain" inline, a different label than the API/UI names. | `context/builder.py:320` | Low |

---

## 2. Proposed future corrections (deferred — migration-free)

All corrections are **proposals for later stages**. None are applied now, per the
stage rules (no renames of public identifiers or DB fields, no API change, no
runtime change). Each is designed to need **no migration**.

| Ref | Correction | Mechanism (no migration, back-compatible) | Target stage |
|---|---|---|---|
| I1/I2 | Rename the profile-projection off "Business Brain." Internal class/helpers → e.g. `BusinessProfileView` / `profile_completeness`. | Rename **internal** symbols; keep `BusinessBrainResponse`/`BusinessBrainUpdate` and `/advisor/brain` as **deprecated aliases** (class alias + unchanged JSON field names) so the API contract is byte-identical. | Stage 1 |
| I2 | Reserve "Business Brain" for the evidence store; "Marketing Brain" for the composition; "Brand Identity" (not "Brand Brain") for the profile slice in new code/docs. | Documentation + new-code convention only; existing identifiers unchanged until a deprecation window passes. | Stage 1+ |
| I3 | Split the `/brand-brain` UI into "Brand Identity" (profile) and "Business Brain" (evidence) sections with distinct headers; keep the route. | Front-end copy/layout only; same endpoints. | Stage 3 (UI) |
| I4 | Adopt `ContextProvenance` as the single **public** tier enum; map `BrainEvidence.kind`, belief status, and Trust `SourceTier` onto it per `PROVENANCE_STANDARD.md §5–6`. | Reference the existing enum from one shared location; no new enum, no field change. | Stage 1 |
| I5 | Apply the belief freshness function to Business Brain evidence at read time in the DNA read model. | Reuse `belief/freshness.effective_confidence`; read-time only, stored values untouched. | Stage 1 |
| I6 | Retire or wrap the `competitors` module behind the Business Brain research path. | Route the legacy entrypoint to the grounded path; delete only after consumers migrate. | Stage 4 |
| I7 | Converge the three composition services onto one `get_business_dna(brand)` read model; `GenerationContext`, `MarketingBrainContext`, and `IntelligenceSignals` become projections. | New read service composes existing stores; old services kept as thin projections during migration (golden-snapshot gated). | Stages 1 & 3 |
| I8 | Always qualify "Business DNA" vs "Creative DNA"; never a bare `dna` in business-intelligence code. | Convention + review check. | ongoing |
| I9 | Align the inline prompt label with the canonical term. | Prompt-string copy only, behaviour-preserving (tested via golden snapshot). | Stage 1 |

---

## 3. Stage 1 implementation prerequisites

Before any Stage 1 code:

1. **These two standards approved** — terminology + provenance (this stage's
   outputs).
2. **Facet list ratified** — the Business DNA facets: Identity, Offer &
   Economics, Audience/Customer, Market/Competitors, Positioning, Learned
   Beliefs, Performance. (Economics is defined now, built in Stage 2.)
3. **Base confirmed** — Marketing Brain (`marketing_brain.build_context`) is the
   base the DNA read model projects from; no second store is created.
4. **Single public provenance tier** — agree that `ContextProvenance` is the one
   public enum and will be referenced (not copied) by the DNA read model.
5. **Golden-snapshot baseline captured** — deterministic fixtures of today's
   `MarketingBrainContext`, `GenerationContext`, and `IntelligenceSignals` outputs
   for a seeded brand, so Stage 1 can prove behaviour preservation.
6. **Consumer inventory frozen** — the consumer table in the terminology doc is
   the migration checklist; any new consumer added before Stage 1 must be added
   to it.
7. **Decisions recorded** (owner): (a) Business Economics as a new table vs JSONB
   on the profile; (b) retire vs wrap the `competitors` module. Both are *noted*,
   not actioned, in this stage.

---

## 4. Test & regression requirements

### This stage (Stage 0) — documentation only
The acceptance bar is **"nothing changed but docs."**
- `git status` shows only added files under `docs/`.
- No change to any `.py`, `.ts`, `.tsx`, schema, migration, or `.env`.
- The six protected files remain untouched.
- No new/removed/renamed public identifier, route, or JSON field.
- OpenAPI schema is unchanged (no router/schema edits).

### Future stages (the regression contract to hold)
- **Golden snapshots**: Stage 1 must reproduce the captured
  `MarketingBrainContext`/`GenerationContext` prompt blocks byte-for-byte (or diff
  only in intentionally relabelled lines, each asserted).
- **API-contract tests**: assert `BusinessBrainResponse`/`BusinessBrainUpdate`
  JSON field names and `/advisor/brain`, `/business-brain` paths are stable across
  the rename (alias coverage test).
- **Provenance unit tests**: every mapping in `PROVENANCE_STANDARD.md §5` has a
  test (kind/status/source → tier).
- **Freshness parity**: when I5 lands, Business Brain evidence decays by the same
  `effective_confidence` the beliefs use (shared-function test).
- **Governance safety**: the 15-invariant human-approval suite
  (`tests/governance`) and tenant-isolation invariants stay green — intelligence
  reconciliation must never widen autonomy or cross a tenant.
- **No-LLM-authority**: tests that confidence/provenance are server-derived
  (belief + trust enforcement) continue to pass and are extended to any surface
  that gains enforcement.

---

## 5. Completion report

**Delivered (3 documents, all under `docs/product/`):**
1. Canonical terminology — 10 terms, each classified store / service / consumer /
   concept, with the existing→canonical name map.
2. Provenance standard — the 5-tier public vocabulary (adopting the existing
   `ContextProvenance`) and the full mapping of evidence kinds, belief confidence,
   freshness, contradictions, and Trust enums into it.
3. This reconciliation plan — 9-item verified inconsistency inventory, 9 deferred
   migration-free corrections mapped to stages, Stage 1 prerequisites, and the
   test/regression contract.

**Rules honoured:** no new Business Brain; no tables/migrations; no runtime
behaviour change; no API-contract change; no renamed public identifiers or DB
fields; protected files untouched; Ollama routing/defaults unchanged; no
commit/push/merge/deploy.

**Verification:** see §4 "This stage"; results recorded with the delivery.
