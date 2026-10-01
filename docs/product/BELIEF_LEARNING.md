# Belief / Learning Layer

DM Tool keeps a **belief memory**: a thin, tenant-scoped graph of what it has
concluded about a brand's marketing, each belief backed by references to
existing evidence (brain evidence, advisor recommendations/outcomes, learning
insights) — never a copy of that evidence. This document describes the completed
lifecycle (Phases 3A–3D) and the one capability deliberately deferred.

## Core invariants

1. **Confidence is evidence-derived, never asserted.** `confidence.py` computes
   confidence as a pure function of supporting vs. contradicting evidence and
   whether any support is experimental (a measured outcome). An LLM can never set
   a belief's confidence, status, scope, or relationships.
2. **No LLM write path.** Beliefs are created and updated only by server code
   holding a trusted `TenantContext`. The conversational agent consumes beliefs
   read-only; there is no tool through which a model can mutate memory.
3. **History is never destroyed.** Contradiction and supersession are modeled as
   relationships (`superseded_by_id`, `parent_belief_id`, status transitions),
   so the chain of how a belief changed stays fully auditable.
4. **Statements are server-templated.** Belief statements are built from
   controlled fields only; free-text outcome content is never interpolated, so
   outcome text can never become instructions (prompt-injection safe).

## Lifecycle

- **3A — memory core.** `models`, `service`, `resolver`, `confidence`: create a
  belief, attach evidence (validated for tenant ownership), derive confidence +
  status, supersede (history retained), resolve a bounded deterministic snapshot.
- **3B — agent consumption.** `modules/agent/beliefs.py` turns the resolver's
  output into a bounded, relevant, read-only context block for one agent turn.
- **3C — automated formation.** `formation.py` maps *evaluated* advisor outcomes
  to belief candidates deterministically and forms/refreshes beliefs through the
  3A service. Correlation, never causation.
- **3D — completed learning lifecycle:**
  - **Cross-belief reconciliation** (`reconcile.py`). When a newly active belief
    opposes an existing one **on a comparable slice**, the weaker/older belief is
    superseded (history preserved). Comparability is strict: two beliefs may only
    conflict when they share the same category and agree on every distinguishing
    scope dimension they both specify (channel / audience / metric / measurement
    window / action kind / …). **Different scopes can never contradict** — a
    belief about Instagram cannot contradict one about email, and a 7-day-window
    belief cannot contradict a 90-day one.
  - **Freshness / decay** (`freshness.py`). At read time the resolver computes an
    `effective_confidence` that decays the stored confidence with age —
    deterministic, bounded `[floor, original]`, never negative, monotonic with
    age, and `0 → 0` (an unvalidated belief is never aged *up* into something that
    looks held). The stored confidence and the historical chain are never
    mutated. Beliefs past their `valid_until` are excluded from the active set but
    remain retrievable as history.
  - **Read API + UI.** `GET /api/v1/beliefs` (authenticated, tenant-derived
    server-side, current by default, history on request, fail-closed) and the
    `/ai-employee/beliefs` page ("What DM Tool believes"), which frames every item
    as an *evidence-backed belief*, not a fact.

## Deferred by design: semantic candidate normalization

Formation currently writes **server-templated** statements. An LLM could propose
more natural wording, but the injection-safety model rests on statements being
built from controlled fields only. Introducing an LLM-authored statement — even
one the server re-validates — widens the attack surface for a marginal
copy-quality gain, so it is **explicitly not done**.

A future safe implementation MUST hold these lines:

- The LLM may influence **only** the human-readable wording of the statement.
- The server retains **sole** authority over tenant/brand, evidence ids, scope,
  confidence, status, relation, supersession, and every authorization decision.
- Any LLM-proposed text is re-run through the existing secret scan, a
  no-causality check (it must not assert causation), and length/So-what bounds
  before it can be stored.

Until then, deterministic templates remain the source of truth. The architecture
is not weakened to claim completion.
