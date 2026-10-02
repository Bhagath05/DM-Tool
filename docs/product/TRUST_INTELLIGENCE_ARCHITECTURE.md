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

**Decision (review-approved): Phase 1 ships NO persistent `claims` table.**
The Trust Layer in Phase 1 is `TrustInput` / `TrustOutput` / `Claim` DTOs and
other typed in-request structures only. All **durable** evidence continues to
come from the existing systems — `BrainEvidence`, `BrainResearchJob`, `beliefs`,
`belief_evidence`, `advisor_outcomes`, provider evidence, and the existing
audit/provenance structures. A `Claim` is materialized per request from those
rows, validated, returned, and discarded; anything worth persisting is promoted
into a **belief** (the existing durable store) or recorded as structured
provenance in `ai_audit` — never into a new claims store.

A future persistent `claims` (and/or `trust_records`) table is justified **only
if all three** become true, and only after an explicit follow-up review:
1. **Cross-turn claim identity** is required beyond what `beliefs` already give
   (e.g. a claim that is neither a durable belief nor a research-evidence row must
   be referenced across sessions).
2. **Queryable trust history** is required (e.g. "show every HIGH-risk claim we
   downgraded last quarter") that `ai_audit` metadata cannot serve efficiently.
3. **Claim-level provenance** must outlive the beliefs/evidence it was derived
   from (independent retention).
Until then, persisting claims is explicitly out of scope.

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

## 7. Confidence derivation (server-derived, independent; LLM is diagnostic only)

**FINAL DECISION.** Authoritative confidence is **server-derived independently**
from structured evidence. Confidence is **DM Tool server policy**, never justified
by how a model "usually" behaves. The LLM-proposed number (if any) is a
**diagnostic/provenance signal only** — recorded for drift analysis in shadow
mode, **never an input** to the authoritative value.

Resolution of the earlier tension ("`final ≤ llm_proposed`" vs "don't let the LLM
lower a well-evidenced value"): we resolve in favor of **independent derivation**.
The server value stands on its own; the server can only ever *lower* an LLM number
(it never raises one), and an LLM asserting a *low* number does **not** drag down a
well-evidenced server value. A large server↔LLM divergence is **recorded** (not
acted on) for review. This satisfies invariant I1 (Trust Layer cannot raise
server-derived confidence) trivially, because the LLM number is not an input.

**Representation: integer 0–100.** Chosen for consistency with the existing
deterministic systems (belief `confidence` int 0–100, advisor `confidence` int,
the `ConfidenceBar` UI), to avoid false precision, and to keep derivation exact
and trivially testable. Generalize the tested belief deriver
(`belief/confidence.py`) into a pure `trust/confidence.py`.

### 7.1 Inputs (all observable/structured — never prose; never provider identity)

| Input | Source | Effect |
|---|---|---|
| evidence quality band | §6 `evidence_quality` | sets **base** and the **ceiling** |
| supporting count | resolvable supporting evidence_ids | **+** diminishing bonus (capped) |
| consistency | agreement among supporting evidence (scope-comparable, same direction) | gate + small **+** |
| contradictions | `reconcile.find_conflicts` | **−** penalty; may force MIXED |
| freshness | `belief/freshness.py` age of underlying evidence | **×** decay multiplier (≤1) |
| comparability | `reconcile.scopes_comparable` for the asked scope | **gate** (fail → INSUFFICIENT) |
| experimental strength | measured outcome / experiment vs observational | **+** bonus |
| claim type | §3/§4 | sets a **type ceiling** |

`llm_proposed` is **not** in this table — it does not affect the derived value.

### 7.2 Deterministic calculation (pure, ordered, integer)

```
0. GATES (any fail → INSUFFICIENT_EVIDENCE, no number):
     comparability fails · band == insufficient · 0 supporting evidence · required metric missing
1. base     = BASE[band]                         # strong 55 · moderate 40 · weak 25
2. support  = PER_SUPPORT(15) * min(support_count, MAX_SUPPORT(3))      # 0..45
3. exp      = EXPERIMENTAL_BONUS(15) if is_measured_outcome else 0
4. consist  = CONSISTENCY_BONUS(5) if all_supporting_same_direction else 0
5. penalty  = PER_CONTRADICTION(20) * min(contradiction_count, MAX_CONTRA(2))   # 0..40
6. raw      = base + support + exp + consist − penalty
7. ceiling  = min( CEILING_BAND[band], CEILING_TYPE[claim_type] )
8. floor    = FLOOR[band]                         # strong 20 · moderate 10 · weak 0
9. derived  = clamp(raw, floor, ceiling)          # integer
10. final   = round( derived * freshness_multiplier(age) )   # effective_confidence; ≤ derived, ≥ decay floor
# llm_proposed is recorded as diagnostic; it is NOT used in steps 1–10.
```

These are **conservative** defaults (strong single-support observation lands ~70,
not 90). Constants are DM Tool policy and sit in `trust/confidence.py` as named
tunables (reusing belief `_PER_SUPPORT=15`, `_EXPERIMENTAL_BONUS=15`,
`_PER_CONTRADICTION=20`, `_CEILING`). Values are the binding v1 policy below;
product may tune, but only through these named constants (never ad-hoc in code).

### 7.3 Bands, ceilings, floors (binding v1)

- **Evidence-quality band** (from §6): `strong` (VERIFIED/DERIVED source, fresh,
  adequate n, no contradictions), `moderate`, `weak`, `insufficient`.
- `CEILING_BAND`: strong **95**, moderate **75**, weak **55**, insufficient **→ none**.
- `BASE[band]`: strong **55**, moderate **40**, weak **25**. `FLOOR[band]`: strong
  **20**, moderate **10**, weak **0**. (`0 supporting evidence → 0`, gated at step 0.)
- `CEILING_TYPE` (claim types do **not** share one ceiling):
  `FACT` **100** (only if backed by a verified deterministic calculation on a
  VERIFIED/FIRST_PARTY/DERIVED source), `OBSERVATION` **85**, `INTERPRETATION`
  **70**, `HYPOTHESIS` **55**, `RECOMMENDATION` = effective confidence of its
  **weakest supporting claim**, then bounded by the consequence floor (§13).
- Applied ceiling `= min(CEILING_BAND, CEILING_TYPE)` — a HYPOTHESIS can never
  reach FACT-level confidence no matter how the LLM phrases it. Nothing reaches
  100 unless it is a verified FACT.

### 7.4 Worked examples (final policy — LLM number is diagnostic only)

| Claim | Type | Band | raw | ceiling | **Derived = Final (×fresh)** | LLM (diagnostic) |
|---|---|---|---|---|---|---|
| "CTR increased 18%" (verified calc, fresh) | FACT | strong | 55+45=100 | min(95,100)=95 | **95** | 88 (recorded; not used) |
| "...coincided with new video" (1 support, fresh) | OBSERVATION | moderate | 40+15=55 | min(75,85)=75 | **55** | 95 (recorded; cannot raise) |
| "Video is plausibly contributing" (1 support) | INTERPRETATION | moderate | 55 | min(75,70)=70 | **55** | 40 (recorded; cannot lower the derived value) |
| "Video may improve conversion" (1 weak signal) | HYPOTHESIS | weak | 25+15=40 | min(55,55)=55 | **40** | 92 (recorded) |
| weak + 1 contradiction | HYPOTHESIS | weak | 25+15−20=20 | 55 | **20** | — |

**Canonical (principle #8):** server derives a 65-ceiling situation → **final 65**
regardless of an LLM "92". Enforced in code, not by prompt.

Properties (inherited from the belief design, already tested): deterministic,
bounded, monotonic with evidence, explainable (`reasons[]`), `0 support → 0`,
**never exceeds the ceiling**, decays with age, and **can only lower** the LLM's
number.

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

## 9. Causality — an evidence hierarchy (not a keyword filter)

**Decision (review-approved): causal language is gated by the *design* of the
evidence behind it, not by keyword matching.** Keyword/pattern detection is used
only to *find* candidate causal statements; whether that language is *allowed* is
decided by the **causal evidence level** the supporting evidence actually meets.
The strongest claim a statement may make is bounded by its evidence level, and
causal language may never exceed the **scope** that was actually measured.

### 9.1 Causal evidence levels

Each supporting-evidence set is deterministically classified into exactly one
level from its structure (how the data was produced), then the claim's permitted
language is bounded by that level.

| Level | Detected from (deterministic) | Allowed claim | NOT allowed | Required disclosure |
|---|---|---|---|---|
| **OBSERVATIONAL** | a single series / before-after with no comparison group (e.g. an advisor outcome's baseline-vs-window lead delta) | "X increased after Y" (temporal only) | "Y caused/drove/led to X" | "temporal only; causation not established" |
| **ASSOCIATIONAL** | two variables co-move across segments, no controlled exposure | "X is associated with Y" / "X tends to accompany Y" | "Y causes X"; any effect-size-as-cause | "association, not causation; confounders not ruled out" |
| **QUASI-EXPERIMENTAL** | a comparison with a non-randomized control / matched cohorts / pre-post with a comparison group | "X is consistent with Y improving Z, with caveats" | unqualified causal claims; generalization beyond the compared groups | "non-randomized; selection/confounding possible; limited to compared cohorts" |
| **CONTROLLED EXPERIMENT** | treatment vs explicit control, defined population/period/metric (not necessarily randomized) | "the experiment provides evidence that the treatment improved Z **vs the control**" | claims outside the measured population/period/treatment/metric | scope: population, period, treatment, control, metric |
| **RANDOMIZED / STRONG CAUSAL** | randomized assignment (or a validated causal-inference design) | "the treatment caused an improvement in Z under the tested conditions" | extrapolation beyond tested conditions / unbounded generalization | scope + randomization basis + confidence interval if available |

### 9.2 Rules

1. **Detect** candidate causal statements (verb/pattern list) — *only to find them*.
2. **Classify** the supporting evidence's level from its structure (above). Today
   the system's measurements are **OBSERVATIONAL** (advisor before/after) to at
   most **QUASI-EXPERIMENTAL** (creative evaluation is a non-randomized
   comparison); there is no randomized design yet, so **no claim may use
   RANDOMIZED-level language** until such designs exist.
3. **Bound** the statement to the level: if the language exceeds what the level
   allows, **downgrade** it to the strongest permitted form and attach the
   required disclosure. Confidence is capped to the level's band (§7).
4. **Scope guard:** causal/quasi-causal language may never exceed the measured
   population, period, treatment, control, and metric. A within-experiment result
   is never presented as a general truth.

Example: OBSERVATIONAL before/after → "Sales increased after the video campaign
launched; the available data does not establish that the video caused it."
This is enforced in code (level classification), not by asking the LLM to be
careful.

---

## 10. Deterministic calculations (calculation registry)

> **Binding v1 registry (formulas, zero-denominator → NOT_COMPUTABLE, provenance
> requirements): see the Phase 1 Implementation Contract §C8.** This section is the
> rationale.

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

## 12. Recommendation validation (a distinct stage)

**Decision (review-approved): the Trust Layer validates recommendations as a
separate stage, not as a by-product of claim validation.** Per the
decision-intelligence principle (TRUST_AND_INTELLIGENCE.md #18): *evidence
supporting a claim is not automatically evidence supporting an action.* A true
claim ("CTR increased 30%") does **not** by itself justify an action ("increase
budget by ₹10 lakh"). The second question requires interpretation + consequence
analysis.

### 12.1 The recommendation pipeline

```
CLAIMS (validated, typed, §3–§9)
  → EVIDENCE (resolvable ids; quality §6)
  → INTERPRETATION (what the claims imply, bounded by causality level §9)
  → RECOMMENDATION (the proposed action)
  → CONSEQUENCE / RISK (level, downside, reversibility — §13)
  → TRUST VALIDATION (status below)
```

### 12.2 What every meaningful recommendation is evaluated for

- **evidence support** — does validated evidence actually bear on *this action*
  (not just on a related claim)?
- **evidence quality** (§6) and **confidence** (§7, weakest supporting claim).
- **scope** — do the supporting claims' scope (audience/channel/metric/window)
  match where the action would apply?
- **contradictions** (§8) — any live opposing evidence?
- **expected effect** — ranged, and traceable to evidence (never a fabricated
  number; §10).
- **downside risk** and **reversibility** — what happens if it's wrong, and can it
  be undone?
- **consequence level** (§13) and **required human approval** (Phases 4A–4C).
- **testability** — how to validate it (HOW-TO-TEST).

### 12.3 Recommendation statuses

| Status | Meaning | When |
|---|---|---|
| `SUPPORTED` | evidence + quality + scope support the action at its consequence level | strong/adequate evidence, no live contradiction, confidence ≥ the floor for its consequence level |
| `QUALIFIED` | directionally supported but bounded by caveats (lower confidence, partial scope, limited attribution) | moderate evidence; must ship with explicit limitations and a softer action ("consider testing…") |
| `INSUFFICIENT_EVIDENCE` | not enough evidence bears on the action | evidence absent / too weak / wrong scope / required metric missing |
| `CONTRADICTED` | live opposing evidence against the action (distinct from MIXED claims) | contradiction directly undermines the action |
| `HIGH_RISK_REQUIRES_REVIEW` | consequence is high and the evidence floor for that consequence is not met | HIGH consequence (§13) without strong+fresh evidence → never auto-advised as SUPPORTED; always human review + approval |

(Taxonomy may be refined in implementation, but these distinctions are required.)

### 12.4 Rules

- A recommendation's **confidence ≤ the derived ceiling of its weakest supporting
  claim**, then further bounded by §13.
- Its **language strength ≤ evidence strength**: "Consider testing UGC" (weak) —
  never "UGC will increase revenue by 25%" (a fabricated metric → rejected by §10).
- A `FACT` that is true but does not bear on the action yields
  `INSUFFICIENT_EVIDENCE` for the recommendation (see Example D).
- The Trust Layer **downgrades/relabels/rejects** recommendations that exceed
  their evidence; it never raises a recommendation's standing because the LLM is
  persuasive.

---

## 13. Consequence / risk model

> **Binding v1 LOW/MEDIUM/HIGH thresholds (evidence band, confidence floor,
> provenance, approval): see the Phase 1 Implementation Contract §C11.** This
> section is the rationale.

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

> **Binding v1 taxonomy is the 7-tier table in the Phase 1 Implementation Contract
> §C10** (VERIFIED_PROVIDER / FIRST_PARTY_DATA / USER_PROVIDED / DERIVED_INTERNAL /
> RESEARCH / MODEL_INFERENCE / UNKNOWN) — provenance quality, **not** a universal
> ranking. The 5-tier sketch below is the earlier rationale; C10 supersedes it.

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

### 19.1 Worked examples (canonical; these are acceptance cases)

**A — fabricated metric (no source data).**
LLM: *"Your campaign increased revenue by 27%."* Data: revenue unavailable
(no connected revenue source). → The metric has no matching verified calculation
(§10) and revenue is calc-only (#3). **Result: REJECT the metric →
`INSUFFICIENT_EVIDENCE`** ("Revenue isn't connected, so I can't confirm a revenue
change"). The 27% is never shown.

**B — unsupported causal claim (observational data).**
LLM: *"Video caused sales to increase."* Data: observational before/after only. →
Causal evidence level = OBSERVATIONAL (§9); causal language not allowed.
**Result: DOWNGRADE** → *"Sales increased after the video launched; the available
data does not establish that the video caused it."* Confidence capped to the
observational band.

**C — incomparable comparison.**
LLM: *"AI creatives are better."* Data: 4 AI vs 2 human creatives on different
audiences. → `scopes_comparable` fails (different audiences; small n). **Result:
`INSUFFICIENT_EVIDENCE` / `INCOMPARABLE_COHORTS`** — no winner declared; state
what would make it comparable (same audience, adequate n).

**D — true claim that does not justify the action (decision intelligence).**
LLM: *"Increase budget by ₹10 lakh."* Evidence: CTR improvement only; no reliable
purchase/revenue attribution. → The CTR claim may be `SUPPORTED`, but it does not
bear on a major spend decision (downstream business impact unestablished).
**Result: recommendation = `INSUFFICIENT_EVIDENCE` (not SUPPORTED)**, and because
the action is HIGH consequence → `HIGH_RISK_REQUIRES_REVIEW` → *"CTR improved, but
downstream business impact isn't sufficiently established to support a major
budget increase; a controlled test would."*

**E — mixed evidence (never hide the inconvenient side).**
Evidence A: video improves CTR. Evidence B: video reduces purchase conversion. →
Both are real and comparable-scope-opposed (§8). **Result: `MIXED_EVIDENCE`,
present both** — *"Video raised CTR but lowered purchase conversion — the evidence
is mixed."* Evidence B is never suppressed.

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

## PHASE 1 IMPLEMENTATION CONTRACT (the agreed, binding interface + rules)

This is the authoritative contract for the *first* implementation phase. It
supersedes looser wording elsewhere in this document. **It is still design** — no
code is written until this contract is approved.

### C1. Scope of Phase 1
- **In:** a pure, server-side `aicmo/modules/trust/` validation layer of
  deterministic functions + in-request DTOs; a read-only provenance resolver; a
  shadow-mode hook in the agent that records (does not yet enforce).
- **Out:** any persistent `claims`/`trust_records` table; any migration; any
  runtime change to what the user sees; any UI change; any new tool/provider; any
  change to auth/RLS/approval/fingerprint/idempotency/audit-security.

### C2. No persistent claims table (Decision 1 — resolved)
Phase 1 uses `TrustInput`, `TrustOutput`, and `Claim` DTOs only. Durable evidence
stays in `BrainEvidence`, `BrainResearchJob`, `beliefs`, `belief_evidence`,
`advisor_outcomes`, provider evidence, and existing audit/provenance. A future
table requires the three conditions in §3 **and** a new review.

### C3. Interfaces (Pydantic DTOs; names indicative)
```
TrustInput:
  tenant                : TenantContext (server-derived; never from the model)
  candidate_answer      : str                  # LLM prose (untrusted)
  candidate_claims      : list[CandidateClaim] # {statement, proposed_type?, proposed_confidence?, cited_evidence_ids[], cited_metrics[]}
  tool_results          : list[...]            # already-structured read-tool outputs
  belief_context        : BeliefResolution     # from the existing resolver
  asked_scope           : Scope?               # audience/channel/metric/window if present
  model_provenance      : {provider, model}?   # PROVENANCE ONLY — never affects any decision (§C-model-independence)

CandidateClaim.proposed_confidence : int?      # DIAGNOSTIC ONLY — recorded, never an input to derivation

Claim (in-request):  claim_id, statement, claim_type, evidence_ids[], source_ids[],
                     source_tier, scope, observed_at, freshness, confidence (int 0-100),
                     confidence_ceiling, causal_level, limitations[], contradictions[], status
Recommendation (in-request): + consequence_level, downside, reversibility,
                     expected_effect, how_to_test, rec_status, requires_approval(bool)
TrustOutput:
  claims                : list[Claim]
  recommendations       : list[Recommendation]
  evidence_status       : ok | MIXED_EVIDENCE | INSUFFICIENT_EVIDENCE
  overall_confidence    : int            # DERIVED, integer 0-100 (never the LLM number)
  downgrades            : list[{target, from, to, reason_code}]
  rejections            : list[{target, reason_code}]
  invariant_violations  : list[reason_code]    # should always be empty; non-empty ⇒ fail closed
  trust_record_id       : str            # correlation into ai_audit
```

**Model-independence (binding):** the Trust Layer is model-agnostic. `provider`/
`model` are retained as provenance only and can never change a rule, a ceiling, a
band, a confidence value, or any decision. There are no per-provider branches.

### C4. Deterministic rules (binding)
1. **Confidence is server-derived independently (integer 0–100); the LLM number
   is diagnostic only.** `final = round(derived × freshness)`, where `derived` is
   §7.2 with ceilings `min(band_ceiling, type_ceiling)` = §7.3 (`FACT≤100,
   OBSERVATION≤85, INTERPRETATION≤70, HYPOTHESIS≤55`; bands `strong≤95,
   moderate≤75, weak≤55, insufficient→none`). `0 supporting evidence → 0`.
   Freshness can only decay. The LLM-proposed number is **not** an input (it is
   recorded for drift only); the server never raises confidence, and a low LLM
   number never depresses a well-evidenced server value. (Canonical: server
   ceiling 65 → **65** regardless of LLM 92.)
2. **Claim type is assigned/validated deterministically**, never by the LLM; the
   Trust Layer may only *demote* a type.
3. **Causal language is bounded by the causal evidence level** (§9), classified
   from evidence structure — not keyword presence. No RANDOMIZED-level language
   exists today. Scope guard: never beyond measured population/period/treatment/
   control/metric.
4. **Every user-visible metric must match a calculation-registry result this
   turn** (§10). Calc-only metrics (CTR, conversion, ROAS, CAC, %-change, budget,
   experiment stats) are never accepted as free LLM text; unmatched → removed.
5. **Contradictions surface as `MIXED_EVIDENCE` with both sides** (§8); different
   scope never contradicts.
6. **Recommendations are validated as a separate stage** (§12) with statuses
   `SUPPORTED | QUALIFIED | INSUFFICIENT_EVIDENCE | CONTRADICTED |
   HIGH_RISK_REQUIRES_REVIEW`; a true claim does not auto-justify an action; a
   HIGH-consequence action without strong+fresh evidence → `HIGH_RISK_REQUIRES_REVIEW`
   and still human-approved (Phases 4A–4C).
7. **Insufficiency is first-class** with a machine reason code (§11); gaps are
   never filled by assumption.
8. **Fail closed:** on any Trust-Layer error, return the honest low-trust /
   insufficient state — never the unvalidated LLM claim.

### C5. Trust Layer boundary (may / may-not) — binding
**May:** accept · downgrade (type and/or confidence) · qualify · reject · mark
`MIXED_EVIDENCE` · mark `INSUFFICIENT_EVIDENCE`.
**May NOT:** retrieve new external data · execute tools · approve actions · bypass
permissions · bypass tenant isolation · raise derived confidence · expose
chain-of-thought.

### C6. First wiring point (shadow mode, T2)
`runtime.run_turn` calls the Trust Layer after SYNTHESIZE; the `TrustOutput` is
**recorded in `ai_audit` only** and the user-visible `AgentResponse` is unchanged.
Enforcement (replacing the LLM's `confidence`/`evidence_status`, dropping/downgrading
claims) is a later, separately-reviewed phase (T3).

### C7. Done-definition for Phase 1 (T0)
Pure functions + (T1) read-only resolver implemented and unit-tested; adversarial
trust tests (§22) green; PG-gated resolver + shadow-record tests green on real
Postgres; the 15 invariants (C14) asserted by tests; read-only-agent / approval /
belief / advisor suites unchanged; Ruff + Pyright clean; **no migration**;
protected files untouched; nothing a user or the agent sees is changed.

### C8. Metric registry (v1 — binding)
Deterministic calculators the Trust Layer may reference; the LLM is never the
calculator. Every result carries `{value, inputs, source_ids, calculated_at}`.
**Zero-denominator and missing/invalid inputs → `NOT_COMPUTABLE` (never 0, never
estimated).** Rounding: ratios/percentages to **1 decimal** for display (computed
at full precision); currency per the account currency formatter (no hardcoded
INR — CLAUDE.md). Monetary metrics (revenue, ROAS, CAC, CPA, spend) require a
`VERIFIED_PROVIDER`/`FIRST_PARTY_DATA` source (§C10) or they are `NOT_COMPUTABLE`.

| Metric | Inputs | Formula | 0-denominator | Missing/invalid | Min evidence / provenance |
|---|---|---|---|---|---|
| impressions | impressions | sum (int ≥0) | — | negative/None → NOT_COMPUTABLE | provider/first-party |
| clicks | clicks | sum (int ≥0) | — | as above | provider/first-party |
| CTR | clicks, impressions | clicks/impressions×100 | impressions=0 → **NOT_COMPUTABLE** | any None → NOT_COMPUTABLE | provider/first-party |
| conversions | conversions | sum (int ≥0) | — | as above | provider/first-party; attribution noted |
| conversion rate | conversions, clicks (or visits) | conv/clicks×100 | denom=0 → **NOT_COMPUTABLE** | as above | provider/first-party + attribution |
| spend | spend | sum (≥0) | — | negative/None → NOT_COMPUTABLE | **VERIFIED_PROVIDER** |
| revenue | revenue | sum (≥0) | — | None → NOT_COMPUTABLE | **VERIFIED_PROVIDER/FIRST_PARTY**; else NOT_COMPUTABLE |
| ROAS | revenue, spend | revenue/spend | spend=0 → **NOT_COMPUTABLE** | either None → NOT_COMPUTABLE | both verified; attribution |
| CAC | spend, new_customers | spend/new_customers | customers=0 → **NOT_COMPUTABLE** | as above | verified spend + verified customers |
| CPA | spend, conversions | spend/conversions | conversions=0 → **NOT_COMPUTABLE** | as above | verified |
| percentage change | current, baseline | (current−baseline)/\|baseline\|×100 | baseline=0 → **NOT_COMPUTABLE** | either None → NOT_COMPUTABLE | comparable scope + comparable periods |

Implementation note: these wrap existing calculators (`analytics/`,
`performance/intelligence/*`, `advisor/outcomes`) — **no new math**; the registry
only *names* them and standardizes the NOT_COMPUTABLE contract.

### C9. Causal-basis catalogue (v1 — binding) + current capability

| Level | Required data / minimum conditions | Allowed claims | Prohibited | Disclosure | Scope | Sufficient for causal language? |
|---|---|---|---|---|---|---|
| OBSERVATIONAL | one series / before-after, **no** comparison group | temporal only ("X rose after Y") | any causal/effect-size-as-cause | "temporal only; causation not established" | the observed window | **No** |
| ASSOCIATIONAL | co-movement across segments, no controlled exposure | "X is associated with Y" | "Y causes X" | "association; confounders not ruled out" | observed segments | **No** |
| QUASI_EXPERIMENTAL | non-randomized control / matched cohorts / pre-post with comparison | "consistent with Y improving Z, with caveats" | unqualified causal; generalization beyond groups | "non-randomized; selection/confounding possible" | compared cohorts only | **Weak/qualified only** |
| CONTROLLED_EXPERIMENT | treatment vs explicit control; defined population/period/metric | "evidence that the treatment improved Z **vs control**" | claims outside measured pop/period/treatment/metric | scope (pop, period, treatment, control, metric) | the experiment | **Yes, scoped** |
| RANDOMIZED / STRONG CAUSAL | randomized assignment or validated causal design | "the treatment caused improvement under tested conditions" | extrapolation beyond tested conditions | scope + randomization basis (+CI if available) | tested conditions | **Yes, scoped** |

**Current DM Tool capability (honest classification — do not pretend otherwise):**
- advisor **outcomes** (`_evaluate_one`, baseline-vs-window lead delta) → **OBSERVATIONAL**.
- **creative evaluation** (AI vs human comparison) → at best **QUASI_EXPERIMENTAL**,
  and frequently fails comparability (different audiences / small n) → treated as
  INSUFFICIENT/INCOMPARABLE rather than quasi-experimental.
- **CONTROLLED_EXPERIMENT** and **RANDOMIZED** → **UNAVAILABLE today.** No current
  data source may be classified at these levels; therefore **no causal language is
  permitted** in v1 beyond scoped quasi-experimental "consistent with" phrasing.
  These levels are reserved for when a real experiment capability exists.

### C10. Source taxonomy (v1 — binding; provenance quality, NOT a universal ranking)

Source tier describes *where evidence came from and its quality for a given
claim* — it is **not** a global "better source" ladder.

| Tier | Example | Supports | Does NOT support | Quantitative? | Causal? | Freshness expectation |
|---|---|---|---|---|---|---|
| VERIFIED_PROVIDER | connected ad/analytics connector, synced OK | metrics, performance FACTs | claims outside the provider's scope | **yes** | only with experiment design (§C9) | per connector cadence; stale → downgrade |
| FIRST_PARTY_DATA | DM Tool-owned data (e.g. leads, publish events) | metrics/FACTs within its scope | provider metrics it doesn't hold | **yes** (in scope) | no (alone) | event-time; stale → downgrade |
| USER_PROVIDED | onboarding profile, manual entry | context, scope, preferences | verified metrics / performance FACTs | **no** | no | until user updates; may go stale silently |
| DERIVED_INTERNAL | calculation-registry output over verified inputs | FACTs iff inputs are VERIFIED/FIRST_PARTY | more than its inputs justify | **yes** (inherits inputs) | inherits inputs | inherits inputs |
| RESEARCH | BrainResearchJob / web research evidence | OBSERVATION/HYPOTHESIS about market/competitors | first-party performance FACTs | **no** (not performance) | no | `discovered_at` age band |
| MODEL_INFERENCE | LLM/world knowledge | general framing, HYPOTHESIS | any FACT, any metric, any causal claim | **no** | **no** | n/a — never a verified source |
| UNKNOWN | unresolvable provenance | nothing presented as verified | any verified FACT | **no** | **no** | treat as stale/unknown |

Only VERIFIED_PROVIDER / FIRST_PARTY_DATA / DERIVED_INTERNAL(over verified) can
back a quantitative FACT. MODEL_INFERENCE and UNKNOWN can never back a FACT, a
metric, or a causal claim.

### C11. Recommendation consequence model (v1 — binding)

| Level | Examples | Required: evidence band | confidence floor | provenance | limitations | human approval |
|---|---|---|---|---|---|---|
| LOW | change headline, test a CTA, generate a creative variant | weak+ (HYPOTHESIS OK) | ≥ 40 | any resolvable | stated | advisory; human runs it |
| MEDIUM | change targeting, shift campaign allocation, change creative strategy | moderate, no live contradiction | ≥ 60 | VERIFIED/FIRST_PARTY/DERIVED | explicit | advisory; human decides |
| HIGH | major budget increase, large-scale/irreversible launch, any consequential external action | **strong + fresh**, scope-matched | ≥ 75 | **VERIFIED_PROVIDER** | explicit + downside + reversibility | **mandatory human approval (Phases 4A–4C)** |

A HIGH recommendation that does not meet its floors → `HIGH_RISK_REQUIRES_REVIEW`
(never auto-`SUPPORTED`), and the action still routes through the existing
approval boundary. The Trust Layer may **raise** these bars; it can **never lower**
the Phase-4 approval requirement.

### C12. Shadow mode (T2) — plan + acceptance gates (binding)

Flow: `LLM candidate → existing response (unchanged, user sees this) → Trust Layer
in shadow → record TrustOutput in ai_audit`.
- **Recorded:** derived confidence, claim types, evidence/source ids, causal
  levels, metric match/mismatch, downgrades/rejections (reason codes), the LLM
  diagnostic confidence, and a server↔LLM divergence number.
- **Not recorded:** prose answers, chain-of-thought, secrets (reuse the `ai_audit`
  scrubber), or anything outside the caller's tenant.
- **Privacy/scope:** tenant-scoped reads only (RLS unchanged); structured
  provenance only.
- **False positives** (Trust Layer would have wrongly downgraded a valid claim):
  reviewed from the recorded reason codes + replay; **false negatives** (would
  have let an unsafe claim through) detected via the adversarial test corpus +
  manual spot audit of recorded assessments.
- **Acceptance gates (evidence-based, not a fixed number of days) — all must hold:**
  1. a **representative sample** across all claim types (≥ N assessments *per*
     claim type FACT/OBSERVATION/INTERPRETATION/HYPOTHESIS/RECOMMENDATION, N set at
     T2 kickoff) and across ≥ the main surfaces;
  2. **zero unresolved critical safety failures** (any fabricated-metric or
     unsupported-causal escape is a hard stop until fixed);
  3. **bounded false-positive rate** below an agreed threshold on the reviewed set;
  4. **bounded false-negative rate** (≈0 for the critical categories) on the
     adversarial corpus;
  5. **deterministic replay agreement** = 100% (same input → same TrustOutput);
  6. all major claim types + all enforcement outcomes exercised at least once.
  Enforcement (T3) may begin only when all six gates pass a review sign-off.

### C13. Enforcement gates (T3) — outcome → action (binding)

| Outcome | Action at T3 | Never |
|---|---|---|
| FABRICATED_METRIC / fabricated revenue/ROAS/etc. | **hard block** the metric → `INSUFFICIENT_EVIDENCE` | never show the number |
| UNSUPPORTED_CAUSAL_CLAIM | **downgrade/qualify** to the permitted causal level + disclosure | never present as causal |
| MIXED_EVIDENCE | **preserve both sides** + qualify | never hide the inconvenient side |
| INSUFFICIENT_EVIDENCE | **state insufficiency** + reason code | never fill the gap |
| CONFIDENCE_OVER_CEILING | **clamp** to derived ceiling | never raise |
| UNRESOLVABLE_EVIDENCE / fabricated evidence | **reject** the claim | never invent evidence |
| RECOMMENDATION_EXCEEDS_EVIDENCE | **downgrade status** (→ QUALIFIED / INSUFFICIENT / HIGH_RISK_REQUIRES_REVIEW) | never auto-SUPPORT |
| scope/limitation issues | **warning/qualify** (attach `limitations[]`) | — |
| provenance/source-tier only | **audit-only** annotation | — |

Enforcement **downgrades/qualifies/blocks/rejects**; it must **never silently
remove evidence** — a dropped claim is always recorded (reason code) in the trust
record, and contradictory evidence is surfaced, not deleted.

### C14. Trust invariants (machine-testable; become tests in T0+)

1. The Trust Layer can never **raise** server-derived confidence.
2. It can never **invent evidence** (every evidence_id resolves to a real row).
3. It can never **invent a metric** (every metric matches a registry result; else NOT_COMPUTABLE).
4. It can never turn **observational** evidence into **causal** evidence.
5. It can never **hide contradictory** evidence (contradictions → MIXED, both shown).
6. It can never **cross tenants** (reads are tenant-scoped; RLS unchanged).
7. It can never **execute tools**.
8. It can never **approve actions**.
9. It can never **bypass authorization/permissions**.
10. It can never **expose chain-of-thought** (structured provenance only).
11. **Missing evidence** can never become a fabricated value (→ INSUFFICIENT/NOT_COMPUTABLE).
12. A **true claim** can never *automatically* justify a consequential recommendation.
13. A **HIGH-consequence unsupported** recommendation can never become executable.
14. **Provider/model identity** can never change a Trust-Layer decision/value.
15. Every **important recommendation** has resolvable provenance (evidence_ids + source_tier).

### C15. Exact T0 scope (what the first code change is, when approved)
Create `aicmo/modules/trust/` containing **pure, in-request, side-effect-free**
code only: the DTOs (C3), `confidence.py` (§7 constants + derivation),
`evidence_quality.py` (§6 bands), `causality.py` (C9 classification + language
bound), `calculations.py` (C8 registry wrapping existing calculators),
`sources.py` (C10 tiering), `recommendation.py` (C11/C12-status logic), and
`invariants.py` (C14 as assertable predicates). **No** wiring into `run_turn`, **no**
provenance DB walk yet (that is T1), **no** migration, **no** UI, **no** tool/
provider, **no** change to auth/RLS/approval/audit-security. Fully unit-tested
(pure) + adversarial trust tests (§22). T0 changes nothing a user or the agent
sees.

---

## Decisions resolved in this revision

- **D1 — Claim persistence:** RESOLVED. No persistent `claims` table in Phase 1;
  DTOs + existing durable stores only (§3, C2). Future-table conditions documented.
- **D2 — Confidence model:** RESOLVED & FIXED. Server-derived **independently**,
  integer 0–100, LLM number **diagnostic only**; exact conservative constants,
  bands, ceilings, floors (§7, C4.1).
- **D3 — Causality:** RESOLVED & FIXED. Evidence-level hierarchy with a binding v1
  catalogue + honest current-capability classification (C9) — CONTROLLED/
  RANDOMIZED marked UNAVAILABLE today.
- **D4 — Recommendation validation:** RESOLVED & FIXED. Separate stage + statuses
  + consequence model (§12, C11) + decision-intelligence principle.
- **D5 — Model-independence:** RESOLVED. Model-agnostic; provider/model =
  provenance only (principle #19, C3, I14).
- **D6 — Metric registry:** RESOLVED (v1). Binding table + NOT_COMPUTABLE contract
  (C8); wraps existing calculators, no new math.
- **D7 — Source taxonomy:** RESOLVED (v1). Seven tiers as provenance quality, not a
  universal ranking (C10).
- **D8 — Enforcement gates:** RESOLVED. Per-outcome hard-block / downgrade /
  qualify / audit-only map; never silently remove evidence (C13).
- **D9 — Trust invariants:** RESOLVED. 15 machine-testable invariants (C14).
- **D10 — T0 scope:** RESOLVED. Pure `trust/` module, nothing wired in (C15).

## Decisions that genuinely need empirical data (cannot be fixed on paper)

These are the *only* remaining opens; each needs the system running in shadow mode
(T2) to resolve, and each has a defined gate rather than a guessed number:

1. **Confidence-constant tuning:** the v1 constants (§7) are conservative and
   binding for launch, but their *calibration* (do derived values match real
   outcomes?) can only be validated against shadow + outcome data; tuning happens
   through the named constants, never ad-hoc.
2. **Shadow thresholds (N, FP-rate, FN-rate):** the exact sample size per claim
   type and the acceptable false-positive bound (C12) must be set from observed
   volume/variance, not guessed; the *gates* are fixed, the *numbers* are empirical.
3. **T3 enforcement style for prose:** rewrite-to-match vs annotate-and-override
   (leaning annotate; final call after shadow shows how often prose diverges from
   the verified claims).
4. **UI surfacing of claim types / source tiers:** a later, separately-reviewed UI
   phase (this phase changes no UI).

---

*Architecture + audit + final Phase-1 contract. No Trust Layer code exists yet.
Review this contract before implementation begins (T0).*
