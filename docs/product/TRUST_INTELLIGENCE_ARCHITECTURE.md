# Trust & Intelligence Layer — Architecture & Audit (Phase 1: design only)

**Status: DESIGN + AUDIT ONLY. Nothing here is implemented.** No migrations, no
schema changes, no agent-runtime changes, no UI changes, no new tools. This
document is the implementation plan to be reviewed before any production code.

Companion: [TRUST_AND_INTELLIGENCE.md](TRUST_AND_INTELLIGENCE.md) (the
non-negotiable principles). Parent constitution: [/CLAUDE.md](../../CLAUDE.md).

Verified baseline commit: `656f536`.

---

## 0. The problem in one paragraph

DM Tool already has strong, *domain-specific* trust mechanisms — but they are
scattered and uneven. The **belief layer** derives confidence deterministically
and never lets the LLM assert it. The **advisor** enforces a 6-field
recommendation contract with a server confidence cap and an explicit
insufficient-data state. **Business-brain evidence** is a typed claim
(fact/observation/hypothesis/recommendation) with provenance. **Outcome
evaluation** is deterministic and feeds learning. But the **conversational agent**
(the new Marketing Brain surface) currently surfaces an **LLM-asserted**
`confidence` and `evidence_status`, with evidence as display labels rather than a
validated provenance chain. The Trust & Intelligence Layer's job is to **unify**
these into one validation gate that sits between candidate reasoning and any
user-visible important conclusion, so confidence is always derived, claims are
always typed and traceable, contradictions and causality are handled
deterministically, and insufficiency stays insufficient.

---

## 1. Current architecture audit

### 1.1 Pipeline today (conversational agent — `modules/agent/runtime.py`)

```
user message
  → MarketingBrainContext (mb_service.build_context)      [retrieve, read-only]
  → belief context (agent/beliefs.build_belief_context)   [retrieve, derived conf]
  → PLAN (LLM, AgentPlan)                                  [reason]
  → execute READ tools (registry) / PROPOSE consequential [retrieve + gate]
  → SYNTHESIZE (LLM, AgentSynthesis)                       [reason]
  → persist + ai_audit                                    [audit]
  → AgentResponse (answer, evidence_status, confidence, evidence[], proposed[])
```

The gap is explicit: there is **no VALIDATE step** between SYNTHESIZE and the
user. `AgentSynthesis.evidence_status` and `.confidence` are produced *by the LLM*
(`runtime.py` passes `synth.confidence` / `synth.evidence_status` straight
through). Prompts forbid fabrication, but nothing deterministically enforces it.

### 1.2 Capability inventory (EXISTING → TRUST ROLE → GAP → REQUIRED CHANGE)

| Existing capability | Where | Trust-layer role | Gap | Required change |
|---|---|---|---|---|
| **Belief memory** (`belief/models.py`: `beliefs`, `belief_evidence`) | Phase 3A | The durable store of typed, scoped, evidence-backed conclusions | Not surfaced as "claims" with claim-type to the agent/UI; scope to beliefs only | Treat beliefs as the canonical persistent claim; add a **claim view** that maps belief → Claim DTO. No schema change needed for v1. |
| **Deterministic confidence** (`belief/confidence.py` `derive_confidence`, ceiling 95, 0-support→0) | 3A | The confidence *derivation* engine | Only used for beliefs; agent/advisor use different/LLM paths | Generalize into a shared `trust/confidence.py` deriver that all claim types call. |
| **Freshness/decay** (`belief/freshness.py` `effective_confidence`, `is_expired`) | 3D | Time-decay of authority | Only applied in the belief resolver | Reuse as-is for all claims; apply at Trust-validation time. |
| **Contradiction/supersession** (`belief/reconcile.py` `scopes_comparable`, `derive_stance`, `find_conflicts`) | 3D | Detects `MIXED_EVIDENCE` and supersession | Belief-only; "different scope never contradicts" rule is exactly right | Reuse `scopes_comparable` + stance logic for claim-level contradiction detection. |
| **Belief formation from outcomes** (`belief/formation.py`) | 3C | Closes the outcome→evidence→belief loop | Only consumes advisor outcomes | Extend inputs over time (not v1); keep correlation-not-causation templating. |
| **BrainEvidence** (`business_brain/models.py`: `kind ∈ {fact,observation,hypothesis,recommendation}`, `category`, `claim`, `confidence`, `status ∈ {active,superseded,contradicted}`, `claim_key`, `superseded_by_id`, `source_url`, `source_type`, `snippet`, `discovered_at`, `research_job_id`) | Business Brain | **Already a typed claim + provenance row** | Confidence is an int set at creation (not continuously derived); not linked to the agent path | Use as the canonical **external/research claim**; derive its effective confidence via freshness at read time. |
| **BrainResearchJob** (`provider`, `source_count`, `started/finished_at`, `status`, `normalized_url`) | Business Brain | Provider + retrieval provenance | — | Use as the SOURCE node for research-derived claims. |
| **DataSourceRef** (`advisor/schemas.py`: key/label/value) | Advisor | Lightweight provenance reference on recommendations | Values are strings, not evidence ids; not resolvable to a quality model | Keep for display; add an **evidence_ids** list for resolvable provenance. |
| **Provenance resolver** (`advisor/creative_evaluation_service.resolve_provenance`, migration `0071_social_asset_provenance`) | Phase 11 | Deterministic AI/human provenance; "never guessed as human" | Creative-only | Pattern to reuse for **source reliability** classification. |
| **Advisor recommendation contract** (`AdvisorRecommendation*`: `recommendation`, `reason/why`, `confidence 0-100`, `impact_category`, `expected_result`, `data_used`) + `InsufficientData` + `confidence_cap=55` | Advisor | The recommendation-validation contract + insufficient-evidence state + a confidence ceiling | `confidence_cap` is enforced via the **prompt**, not a server clamp; `data_used` isn't resolvable evidence | Server-clamp confidence to the derived ceiling; attach evidence_ids. |
| **Outcome evaluation** (`advisor/outcomes.py` `evaluate_due_outcomes`, `_evaluate_one` → `evaluation_status ∈ {evaluated, insufficient_data}`, `effectiveness_score`, `delta_summary`) | Advisor | Deterministic outcome measurement | Lead-delta only; one metric | Reuse as the canonical outcome evaluator; broaden metrics later (not v1). |
| **Deterministic metric calc** (`analytics/service.py`, `performance/intelligence/*`, `marketing_analytics/creative_evaluation.py`) | Analytics/Perf | The calculators (CTR, conversion, grouping, creative/audience intelligence) | No single registry; not addressable by the Trust Layer as "verified calculations" | Introduce a thin **calculation registry** that names + wraps existing calculators (no new math). |
| **Agent response contract** (`agent/schemas.py`: `evidence_status ∈ {ok, INSUFFICIENT_EVIDENCE}`, `confidence`, `evidence[]`, `reasoning_summary`, `proposed_actions[]`) | Phase 2/4B | The user-facing response envelope | **`confidence`/`evidence_status` are LLM-set**; evidence is labels, not resolvable | Add a server-computed **TrustAssessment**; make the LLM number advisory-only. |
| **ai_audit** (`ai_audit/service.record_ai_generation`, `_strip_content` scrubber, token counts, no content) + **audit_events** (`audit/service.record`, entity.verb, before/after) | — | The structured audit substrate (no chain-of-thought, no secrets) | No trust-specific record (claim/evidence/confidence correlation) | Add a **trust audit record** built on the same substrate (structured provenance only). |
| **Approval pipeline** (`agent_actions/*`: state machine, fingerprint, idempotency, audit, execute-after-approval) | 4A–4C | Consequence gate for actions | — | Unchanged. Trust Layer may raise required-evidence for high-consequence recommendations but never alters the action boundary. |
| **Prompt-injection fencing** (`agent/prompts.untrusted_block`, secret regex in `belief/service`, `ai_audit` scrubber) | 2–3 | Treats retrieved data as data; blocks secret-shaped text | — | Reuse; the Trust Layer treats candidate LLM output as *data to validate*, not instructions. |

**Conclusion of audit:** ~80% of the Trust Layer already exists as parts. The
missing ~20% is (a) a **unifying claim + trust-assessment representation**, (b) a
**validation gate** in the agent path, (c) a **calculation registry** boundary,
and (d) a **deterministic causal-language + metric-fabrication guard**.

---

## 2. Trust Layer boundary (where it runs, I/O, powers)

A **pure, server-side validation service** — `aicmo/modules/trust/` — invoked
*after* candidate reasoning and *before* any user-visible important conclusion is
returned or persisted. It is advisory/validating only: it cannot retrieve new
data, call tools, act, or widen access.

```
TrustInput  (candidate)            TrustOutput (verified/qualified)
──────────────────────            ────────────────────────────────
tenant (server-derived)           claims[]        (typed, with derived confidence)
candidate_answer (LLM text)       evidence_status (ok | MIXED | INSUFFICIENT)
cited evidence refs (by id)       overall_confidence (derived, capped)
proposed metrics (name+inputs)    downgrades[]    (what was softened + why)
proposed causal statements        rejections[]    (what was removed + why)
candidate confidence (LLM)        safe_answer     (optional server-sanitized text)
                                  trust_record_id (audit correlation)
```

**Powers (what it may do):**
- **Accept** a claim as-is (all checks pass).
- **Downgrade** a claim's *type* (fact→observation, causal→correlational) and/or
  its *confidence* (clamp to the derived ceiling).
- **Mark** `INSUFFICIENT_EVIDENCE` or `MIXED_EVIDENCE`.
- **Reject** a claim (drop it from the response) when it asserts a fabricated
  metric or unresolvable evidence.
- **Replace** an LLM-stated metric with the deterministically calculated value,
  or remove it if no verified calculation exists.

**It may never:** invent evidence, raise confidence above the derived ceiling,
execute anything, cross tenants, or expose chain-of-thought.

**Determinism rule:** every decision the Trust Layer makes is a pure function of
structured inputs (evidence rows, quality signals, freshness, calculation
results). The LLM is never asked "is this trustworthy?"

---

## 3. Claim model

Reuse before inventing. The persistent canonical claim is the **belief**
(`beliefs`) for internal conclusions and **BrainEvidence** for research/external
claims. For the Trust Layer we introduce a **transient, in-request `Claim` DTO**
(Pydantic, not a new table in v1) that normalizes both plus ad-hoc agent claims:

```
Claim (DTO; v1 = in-request, not persisted unless promoted to a belief)
  claim_id           # stable within the turn; belief/evidence id if backed
  statement          # bounded, server-templated or sanitized LLM text
  claim_type         # FACT | OBSERVATION | INTERPRETATION | HYPOTHESIS | RECOMMENDATION
  evidence_ids       # resolvable refs (brain_evidence / advisor_outcome / belief / calc)
  source_ids         # BrainResearchJob / provider / internal-calc / user-provided
  scope              # audience/channel/metric/window (reuses belief scope shape)
  observed_at        # provenance timestamp (discovered_at / evaluated_at)
  freshness          # derived: fresh | aging | stale | expired (belief/freshness.py)
  confidence         # DERIVED (trust/confidence.py); never the raw LLM number
  confidence_ceiling # from evidence quality (§6/§7)
  limitations[]      # explicit caveats (sample size, attribution, comparability…)
  contradictions[]   # claim_ids / evidence_ids that oppose it (reconcile.py)
  status             # active | mixed | superseded | contradicted | insufficient
```

**Claim-type ladder (monotonic trust, never collapsed):**
FACT > OBSERVATION > INTERPRETATION > HYPOTHESIS > RECOMMENDATION — these carry
different confidence ceilings and render differently (§4). A claim may only be
*promoted* to a stronger type by stronger evidence, and the Trust Layer only ever
*demotes*.

**Why a DTO, not a table, in v1:** beliefs + brain_evidence already persist the
durable claims; a per-turn DTO avoids a premature schema and a duplicate store.
A `claims` table is a *later* option only if we need cross-turn claim identity
beyond what beliefs provide (see §22, Open Questions).

---

## 4. FACT / INTERPRETATION / HYPOTHESIS / RECOMMENDATION flow

| Type | Example | Confidence ceiling (proposed) | Evidence bar | Renders as |
|---|---|---|---|---|
| FACT | "CTR increased 18%." | up to 100 only if from a **verified deterministic calculation** on first-party data | calculated metric + provider-verified source | metric block, "Evidence-backed" |
| OBSERVATION | "The increase coincided with the new video creatives." | ≤ derived (evidence-quality capped) | ≥1 resolvable evidence, comparable scope | observation line |
| INTERPRETATION | "Video is plausibly contributing." | capped lower (e.g. ≤ 70 unless experimental) | observation + consistency, no contradiction | interpretation, hedged |
| HYPOTHESIS | "Video may improve conversion." | capped (e.g. ≤ 55) | ≥1 signal; explicitly unproven | hypothesis block |
| RECOMMENDATION | "Run a video-vs-static experiment." | inherits supporting-claim ceiling + consequence rules (§13) | traceable WHY/EVIDENCE/EXPECTED/HOW-TO-TEST | recommendation block |

Flow (no implementation yet):
- **Backend:** the Trust Layer assigns/validates `claim_type` deterministically
  (e.g. a metric with a verified calculation ⇒ FACT; a causal verb without a
  controlled basis ⇒ demote to OBSERVATION/INTERPRETATION per §9).
- **Agent:** `AgentResponse` gains a typed `claims[]` (additive) alongside the
  existing `answer`; the LLM proposes, the Trust Layer types.
- **Generative UI (already built, not changed now):** the Phase-"Brain" primitives
  already distinguish evidence/recommendation/approval/insufficient; a later
  phase maps `claim_type` → the right primitive. **UI unchanged in this phase.**

---

## 5. Provenance model

Reuse existing ids; do not build a parallel store. The provenance chain the Trust
Layer must be able to reconstruct to answer *"why did DM Tool say this?"* (without
chain-of-thought):

```
Claim
  → evidence_ids → belief_evidence / brain_evidence / advisor_outcome / calc_result
      → source_ids → BrainResearchJob(provider, normalized_url) / provider connector
                      / internal calculation (named) / user-provided profile
          → data   → the stored row's fields (snippet, metric inputs, counts)
              → timestamp (discovered_at / evaluated_at / calc run)
                  → scope (audience/channel/metric/window)
                      → transformation (named calculation or belief-derivation rule)
                          → conclusion (the claim statement)
```

Everything needed already exists as ids:
`belief_evidence.ref_kind/ref_id`, `brain_evidence.id/source_url/research_job_id`,
`advisor_outcomes.id/effectiveness_score`, `BrainResearchJob.provider`. The Trust
Layer adds a **read-only provenance resolver** that walks these ids and returns a
structured chain — never free text, never reasoning traces.

---

## 6. Evidence quality (deterministic, not an LLM score)

A pure function `evidence_quality(signals) → {score 0-100, band, reasons[]}` over
**observable, stored** signals only:

| Signal | Source today | Contribution |
|---|---|---|
| source reliability | §16 classification (verified/derived/inferred/user/unknown) | large |
| provider verification | `BrainResearchJob.provider`, connector status | large |
| freshness | `belief/freshness.py` age bands | decay multiplier |
| sample size | counts (`source_count`, lead counts in outcomes) | gate + scale |
| comparability (scope match) | `reconcile.scopes_comparable` | gate |
| attribution quality | connector attribution completeness | cap |
| experimental design | outcome is a measured experiment vs observational | bonus |
| missing data | nulls in required fields | penalty / gate |
| contradictions | `reconcile.find_conflicts` | penalty / MIXED |
| statistical strength | effect size / delta magnitude (outcomes) | scale |

**No arbitrary LLM number.** If a numeric score is used it is this function's
output, fully explainable via `reasons[]`. Bands (proposed): `strong` (verified +
fresh + adequate n + no contradictions), `moderate`, `weak`, `insufficient`.

---

## 7. Confidence derivation

Generalize the proven belief deriver (`belief/confidence.py`) into
`trust/confidence.py`:

```
confidence = clamp(
    base(evidence_quality.band)                 # strong/moderate/weak → base
  + support_bonus(supporting_count)             # diminishing, capped (reuse MAX_COUNTED)
  + experimental_bonus(is_measured_outcome)     # reuse _EXPERIMENTAL_BONUS
  − contradiction_penalty(contradicting_count)  # reuse _PER_CONTRADICTION
  , 0, ceiling(evidence_quality.band, claim_type) )          # hard ceiling
  then × freshness_multiplier(age)              # reuse effective_confidence
```

Properties (all inherited from the belief design, which is already tested):
deterministic, bounded, monotonic with evidence, explainable, `0 support → 0`,
**never exceeds the ceiling**, decays with age. The **ceiling** is set by evidence
quality AND claim type (a HYPOTHESIS cannot reach FACT-level confidence no matter
how the LLM phrases it). The LLM's self-reported number is only ever used to
*lower* (never raise) — matching rule #8.

---

## 8. Contradiction handling

Reuse `belief/reconcile.py` verbatim in spirit:
- `scopes_comparable(a, b)` — two claims only conflict when same category and
  agreement on every shared distinguishing scope dimension (channel/audience/
  metric/window). **Different scope never contradicts** (the safety property).
- When comparable claims assert opposite stances on the same metric, the Trust
  Layer returns `MIXED_EVIDENCE` and **presents both**, e.g. "Video raised CTR
  but lowered purchase conversion — evidence is mixed." It does not pick a winner
  for the user; it may rank by evidence quality but must show the contradiction.
- Supersession (a newer, stronger claim replacing an older) reuses the existing
  `supersede_belief` lineage — history preserved.

---

## 9. Correlation vs causation safeguards (deterministic)

A pure **causal-language gate** over candidate statements:
1. Detect causal assertions deterministically (verb/pattern list: "caused",
   "because of", "drove", "led to", "increased … by doing", etc.).
2. Check for a **causal basis** attached to the supporting evidence:
   controlled experiment / randomized comparison / validated causal method
   (today: an advisor *outcome* is a before/after measurement — **observational**,
   not causal; creative evaluation is a comparison but not randomized).
3. If no sufficient basis → **downgrade** the statement to observation/temporal
   language ("Sales rose after the video launched; available data does not
   establish causation") and cap confidence accordingly.

Ordinary observational correlation **never** auto-becomes causal language. This
is enforced in code, not by asking the LLM to be careful.

---

## 10. Deterministic calculations (calculation registry)

The LLM explains verified numbers; it is not the calculator.

- Introduce `trust/calculations.py` — a **registry** that *names and wraps the
  existing calculators* (no new math): e.g. `ctr`, `conversion_rate`, `roas`,
  `cac`, `pct_change`, `budget_total`, `experiment_delta`. Each entry:
  `(name, input schema, pure fn, output unit, source requirements)`.
- Flow: `RAW DATA → registry fn → VALIDATED RESULT (value, inputs, source_ids,
  calculated_at) → LLM explanation`.
- The Trust Layer: any metric the LLM states in prose is **matched** to a
  registry result; if there is no matching verified result, the metric is
  **removed** (rule #2/#3). The LLM may only reference metric *names/values that
  the registry produced this turn*.
- Critical metrics (CTR, conversion, ROAS, CAC, revenue/%-change, budget,
  experiment stats) are flagged **calc-only**: never acceptable as free LLM text.

---

## 11. Insufficient-evidence behavior (first-class)

`INSUFFICIENT_EVIDENCE` already exists in three places (advisor `InsufficientData`,
agent `evidence_status`, belief "unvalidated"). Make it a **single typed terminal
state** the Trust Layer can emit, with a machine-readable reason:

| Reason code | Trigger (deterministic) |
|---|---|
| `SMALL_SAMPLE` | count below a per-metric threshold |
| `INCOMPLETE_ATTRIBUTION` | connector attribution missing/partial |
| `STALE_DATA` | freshness = expired |
| `CONFLICTING_EVIDENCE` | unresolved contradiction → (MIXED, not INSUFFICIENT, when both sides are real) |
| `PROVIDER_UNAVAILABLE` | required connector not connected |
| `INCOMPARABLE_COHORTS` | `scopes_comparable` fails for the requested comparison |
| `MISSING_METRIC` | required metric not present in data |

The system states which reason(s) apply and **never fills the gap with an
assumption**. The UI already renders an insufficient-evidence block (unchanged).

---

## 12. Recommendation validation

A recommendation passes only if it is **traceable and bounded**:
- carries WHY, EVIDENCE (resolvable ids), CONFIDENCE (derived), LIMITATIONS,
  EXPECTED EFFECT (ranged when uncertain), HOW-TO-TEST — reusing the existing
  advisor 6-field contract and extending `data_used` with `evidence_ids`;
- its confidence ≤ the derived ceiling for its weakest supporting claim;
- its strength of language ≤ evidence strength — "Consider testing UGC" (weak)
  not "UGC will increase revenue by 25%" (fabricated metric → rejected by §10).

The Trust Layer rejects/relabels recommendations that exceed their evidence.

---

## 13. Consequence / risk model

Each recommendation gets a deterministic **consequence level** from the action it
implies (reusing the autonomy `action_type` vocabulary + the agent-action
registry's `operation_class`):

| Level | Examples | Required evidence floor | Authorization |
|---|---|---|---|
| LOW | test a new headline, draft a post | weak+ (hypothesis OK) | advisory; still human-run |
| MEDIUM | shift creative mix toward UGC, change cadence | moderate, no live contradiction | advisory; human decides |
| HIGH | substantially increase ad spend, launch campaign, publish | strong + fresh; consequence tools → **approval required** | **human approval (Phases 4A–4C), unchanged** |

Higher consequence ⇒ higher evidence floor ⇒ still human-authorized. The Trust
Layer can *raise the evidence bar* for a high-consequence recommendation; it can
**never lower the approval requirement**.

---

## 14. Outcome learning loop

Already present end-to-end; the Trust Layer formalizes it as the learning spine:

```
RECOMMENDATION (advisor) → APPROVAL (agent_actions, if consequential)
  → EXECUTION (verified result only) → OUTCOME (advisor_outcomes)
  → EVALUATION (deterministic _evaluate_one) → NEW EVIDENCE
  → BELIEF UPDATE (formation.py + reconcile.py: supports/contradicts, supersede)
```

A recommendation that proved wrong becomes a **contradicting** evidence row and
can flip/supersede a belief (history retained) — so the system can later say
"a previous recommendation was not supported by subsequent evidence." No new
store; this reuses beliefs + outcomes.

---

## 15. Trust audit trail

Built on the existing audit substrate (`audit_events` + `ai_audit_events`), add a
**trust record** (structured provenance only; no secrets, no chain-of-thought):

```
recommendation_id / claim ref · tenant · timestamp · context (question hash/topic)
evidence_ids[] · source_ids[] · evidence_freshness · derived_confidence · ceiling
contradictions[] · limitations[] · claim_type · consequence_level
approval_state (if any) · execution_state (if any) · outcome_ref · evaluation_ref
downgrades[] (what the Trust Layer softened + machine reason)
```

v1 can record this inside `ai_audit` metadata (already scrubbed) keyed by a
`trust_record_id`; a dedicated `trust_records` table is a later option only if we
need queryable trust history (§22).

---

## 16. Source reliability model

A deterministic classifier `source_reliability(source) → tier` reusing the
provenance-resolver pattern (`resolve_provenance`, never-guess-human):

| Tier | Meaning | Detected from |
|---|---|---|
| `VERIFIED` | first-party provider-confirmed data | connected connector + successful sync |
| `DERIVED` | internal analytics computed from verified data | calculation registry output over VERIFIED inputs |
| `USER_PROVIDED` | business profile / manual entry | onboarding/profile origin |
| `INFERRED` | model knowledge / heuristic | no external source row |
| `UNKNOWN` | provenance not resolvable | missing/unresolvable source_ids |

The UI (later) must visibly distinguish these; INFERRED/UNKNOWN can never be
presented as a verified FACT. All sources are **not** treated equally in §6/§7.

---

## 17. Freshness

Reuse `belief/freshness.py` (`effective_confidence`, `is_expired`) for **all**
claim types, not just beliefs:
- claims: effective confidence decays with age of the underlying evidence;
- recommendations: a recommendation on stale evidence is downgraded / re-flagged;
- provider evidence: `discovered_at` age drives a freshness band;
- expired validity → excluded from "current," retained as history.

Old evidence never silently keeps full authority.

---

## 18. Agent integration boundary

Target: `RETRIEVE → REASON → VALIDATE → RESPOND` (today it is RETRIEVE → REASON →
RESPOND). **Not implemented in this phase** — only the boundary is specified.

- **Where it runs:** a single call in `runtime.run_turn`, after SYNTHESIZE and
  before building `AgentResponse` (and before persisting the assistant message).
- **Receives:** server-derived tenant; the candidate `AgentSynthesis`; the
  executed tool results (already structured); the resolved belief context; any
  metrics the LLM referenced (name + inputs).
- **Returns:** a `TrustAssessment` → typed `claims[]`, derived
  `overall_confidence`, server `evidence_status`, `downgrades[]`, `rejections[]`,
  and a `trust_record_id`.
- **Can reject:** claims citing unresolvable evidence or fabricated metrics.
- **Can downgrade:** claim type (fact→observation, causal→correlational) and
  confidence (clamp to ceiling).
- **Can mark unsupported:** `INSUFFICIENT_EVIDENCE` / `MIXED_EVIDENCE`.
- **Output precedence:** the server `evidence_status`/`confidence` **replace** the
  LLM's in `AgentResponse`; the LLM `answer` text is kept only if it survived the
  metric/causal/evidence gates (else a server-sanitized variant or the honest
  insufficient-evidence state is shown).

This preserves the existing read-only + approval boundaries exactly; the Trust
Layer is pure and cannot act.

---

## 19. Failure modes (fail safe)

| Condition | Behavior |
|---|---|
| Evidence unavailable / unresolvable | `INSUFFICIENT_EVIDENCE` (not a guess) |
| Provider verification unavailable | source tier = `UNVERIFIED`; no FACT claim |
| Contradictory real evidence | `MIXED_EVIDENCE`; show both sides |
| Calculation failure / missing inputs | **do not display** the metric |
| Stale evidence | downgrade confidence / relevance (freshness) |
| Missing attribution | state attribution limitation in `limitations[]` |
| Unsupported causal claim | downgrade to correlation/observation |
| Unknown provenance | not presented as verified fact |
| Trust Layer itself errors | **fail closed**: return the honest low-trust / insufficient state, never the unvalidated LLM claim |

---

## 20. Security considerations

The Trust Layer is a **pure validation gate**, not an authority:
- tenant is always server-derived; it reads only within the caller's tenant (RLS
  + service-layer brand filter unchanged);
- it performs **no** writes to consequential state, **no** tool execution, **no**
  approval transitions, **no** access widening;
- it treats the candidate LLM output as **untrusted data to validate** (same
  stance as `untrusted_block`), so a prompt-injected "set confidence 99 / approve
  this" in retrieved content or candidate text cannot move it — decisions are pure
  functions of stored evidence;
- it stores structured provenance only (no secrets — reuse the `ai_audit`
  scrubber; no chain-of-thought);
- action fingerprints, idempotency, and the approval state machine are untouched.

The Trust Layer must never become a bypass around any existing control.

---

## 21. Implementation phases (proposed; each independently shippable + tested)

- **T0 — contracts (no behavior change):** `aicmo/modules/trust/` with pure DTOs
  (`Claim`, `TrustAssessment`, `EvidenceQuality`) + `confidence.py` (generalized
  deriver) + `causality.py` gate + `calculations.py` registry wrapping existing
  calculators. Pure functions only; unit-tested; nothing wired in.
- **T1 — provenance resolver (read-only):** walk existing ids → structured chain;
  tests over beliefs/brain_evidence/outcomes.
- **T2 — agent VALIDATE step (shadow mode):** call the Trust Layer in
  `run_turn`, **record** the assessment in `ai_audit`, but **do not** yet change
  the user-visible response. Compare LLM vs derived confidence in audit. (No UI
  change; reversible.)
- **T3 — enforce:** server `evidence_status`/`confidence` replace the LLM's in
  `AgentResponse`; metric/causal/evidence gates drop/downgrade claims.
- **T4 — typed claims to the response + UI mapping:** add `claims[]`; map
  `claim_type` to the already-built generative-UI primitives.
- **T5 — recommendation consequence floors + trust record table (if needed).**

Gate between phases: a design review, full test suite, Postgres-backed tests, and
no regression to the read-only/approval boundaries.

---

## 22. Testing strategy

- **Pure unit tests** (no DB) for every deterministic function: confidence
  derivation (bounds/monotonicity/ceiling/0-support), evidence quality bands,
  causal-language gate (causal → downgrade), calculation registry (known
  input→output), freshness decay, `scopes_comparable` reuse.
- **Adversarial/trust tests:** fabricated metric in candidate → removed; LLM
  "confidence 99" with weak evidence → clamped to ceiling; unsupported causal
  phrasing → downgraded; contradictory evidence → MIXED with both sides; stale
  evidence → downgraded; unresolvable evidence → INSUFFICIENT; prompt-injected
  "approve/raise confidence" in candidate/retrieved text → ignored.
- **PG-gated integration:** provenance resolver over real beliefs/brain_evidence/
  outcomes; shadow-mode assessment recorded in `ai_audit`; tenant isolation of
  the resolver.
- **Regression pins:** read-only agent behavior, approval state machine, and the
  existing belief/advisor suites stay green. Run on real Postgres (the repo's
  `TEST_DATABASE_URL` path) — PG-gated tests reported honestly, never skipped-as-passed.

---

## 23. Migration strategy

- **T0–T4 require no migration** — they reuse `beliefs`, `belief_evidence`,
  `brain_evidence`, `advisor_outcomes`, `ai_audit_events`, `audit_events`. The
  `Claim`/`TrustAssessment` are in-request DTOs; the trust record lives in
  `ai_audit` metadata.
- **Possible later migration (T5, only if justified):** a `trust_records` table
  for queryable trust history, and/or a `claims` table if cross-turn claim
  identity beyond beliefs is needed. If added: single Alembic head, org-scoped
  RLS (reuse `rls.create_policy_sql`), upgrade+downgrade tested on Postgres,
  no change to protected files.

---

## Open questions (for review before any code)

1. **Claim persistence:** are per-turn DTOs + beliefs enough, or do we need a
   first-class `claims` table from the start? (Recommendation: start with DTOs.)
2. **Confidence ceilings:** exact ceiling per (evidence band × claim type) — needs
   product sign-off against the existing CLAUDE.md confidence bands (80/60/40).
3. **Enforcement vs advisory for the agent's prose answer:** at T3, do we *rewrite*
   the LLM answer to match the verified claims, or only annotate + override the
   structured fields and drop offending sentences? (Rewriting risks a second LLM
   pass; annotation is safer.)
4. **Causal-basis catalogue:** which existing measurements count as a valid causal
   basis? (Today: none are randomized; advisor outcomes are before/after
   observational, creative-eval is a non-randomized comparison.)
5. **Metric registry coverage:** confirm the canonical calculators to wrap and
   which metrics are "calc-only" (CTR, conversion, ROAS, CAC, %-change, budget,
   experiment stats proposed).
6. **Shadow-mode duration (T2):** how long to run shadow comparison before
   enforcing, and the acceptance criterion (e.g. derived ≤ LLM confidence in N%
   of turns).
7. **Source tiers in UI:** when (which later phase) do VERIFIED/DERIVED/INFERRED/
   UNKNOWN badges appear, given this phase makes no UI change.

---

*This is an architecture + audit deliverable only. No Trust Layer code exists yet.
Review this plan before implementation begins.*
