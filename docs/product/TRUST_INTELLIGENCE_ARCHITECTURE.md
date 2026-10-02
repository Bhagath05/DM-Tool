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

## 7. Confidence derivation (server-derived; LLM may only lower)

**Decision (review-approved): authoritative confidence is always server-derived.**
The LLM may emit a *proposed* confidence signal, but it is never authoritative.
The server derives confidence from structured evidence signals, then takes the
**minimum** of (derived, LLM-proposed). The server can therefore only ever
**reduce** an LLM number — never raise it because the model "sounds certain."

Generalize the proven belief deriver (`belief/confidence.py`) into a pure
`trust/confidence.py`.

### 7.1 Inputs (all observable/structured — never prose)

| Input | Source | Effect |
|---|---|---|
| evidence quality band | §6 `evidence_quality` | sets **base** and the **ceiling** |
| supporting count | resolvable supporting evidence_ids | **+** diminishing bonus (capped) |
| consistency | agreement among supporting evidence (scope-comparable, same direction) | **+** / gate |
| contradictions | `reconcile.find_conflicts` | **−** penalty; may force MIXED |
| freshness | `belief/freshness.py` age of underlying evidence | **×** decay multiplier (≤1) |
| comparability | `reconcile.scopes_comparable` for the asked scope | gate (fail → INSUFFICIENT) |
| experimental strength | measured outcome / experiment vs observational | **+** bonus |
| claim type | §3/§4 | sets a **type ceiling** (below) |
| llm_proposed | the candidate | **only lowers**: `min(derived, llm_proposed)` |

### 7.2 Deterministic calculation (pure, ordered)

```
0. comparability gate:  if scope not comparable OR required evidence missing → INSUFFICIENT_EVIDENCE (no number)
1. base          = BASE_FOR_BAND[quality_band]            # strong/moderate/weak/insufficient
2. support       = PER_SUPPORT * min(supporting_count, MAX_COUNTED_SUPPORT)   # diminishing, reuse belief tunables
3. experimental  = EXPERIMENTAL_BONUS if is_measured_outcome else 0
4. penalty       = PER_CONTRADICTION * min(contradicting_count, MAX_COUNTED_CONTRA)
5. raw           = base + support + experimental − penalty
6. ceiling       = min( CEILING_FOR_BAND[quality_band], CEILING_FOR_TYPE[claim_type] )   # hard cap
7. floor         = FLOOR_FOR_BAND[quality_band]           # never claim more certainty than the band allows, never negative
8. derived       = clamp(raw, floor, ceiling)
9. fresh         = round(derived * freshness_multiplier(age))     # reuse effective_confidence (monotonic, ≤ derived)
10. final        = min(fresh, llm_proposed_or_100)        # LLM may ONLY reduce
```

All constants reuse / generalize the already-tested belief tunables
(`_BASE`, `_PER_SUPPORT`, `_MAX_COUNTED_SUPPORT`, `_EXPERIMENTAL_BONUS`,
`_PER_CONTRADICTION`, `_CEILING=95`). Exact values per band/type are set in the
**Phase 1 Implementation Contract** (below) and need product sign-off against the
CLAUDE.md bands (80/60/40).

### 7.3 Ceilings and floors

- **Evidence-quality ceiling** `CEILING_FOR_BAND`: `strong ≤ 95`, `moderate ≤ 75`,
  `weak ≤ 55`, `insufficient → no confidence` (INSUFFICIENT_EVIDENCE). (95 reuses
  the belief ceiling — nothing is ever 100 unless it is a verified FACT, §7.4.)
- **Claim-type ceiling** `CEILING_FOR_TYPE` (these do **not** share one ceiling):
  - `FACT` (verified deterministic calculation on verified data): up to **100**.
  - `OBSERVATION`: ≤ **85**.
  - `INTERPRETATION`: ≤ **70**.
  - `HYPOTHESIS`: ≤ **55**.
  - `RECOMMENDATION`: inherits the **weakest supporting claim's** effective
    confidence, then further bounded by the consequence/risk model (§13).
- The applied ceiling is `min(band_ceiling, type_ceiling)` — so a HYPOTHESIS can
  never reach FACT-level confidence regardless of how the LLM phrases it.
- **Floor** keeps a once-supported claim from collapsing to 0 through age alone
  (freshness decays to a floor, never below), while `0 supporting evidence → 0`.

### 7.4 Confidence by claim type (worked)

| Claim | Type | Band | Derived | Type ceiling | LLM proposed | **Final** |
|---|---|---|---|---|---|---|
| "CTR increased 18%" (verified calc) | FACT | strong | 90 | 100 | 88 | **88** (LLM lowered it) |
| "...coincided with new video" | OBSERVATION | moderate | 72 | 85 | 95 | **72** (LLM can't raise) |
| "Video is plausibly contributing" | INTERPRETATION | moderate | 70 | 70 | 90 | **70** |
| "Video may improve conversion" | HYPOTHESIS | weak | 60 | 55 | 92 | **55** (type ceiling binds) |

**Canonical example (rule #8):** LLM proposed **92**, server evidence ceiling **65**
→ **final 65**. Documented and enforced in code, not by prompt.

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

Claim (in-request):  claim_id, statement, claim_type, evidence_ids[], source_ids[],
                     scope, observed_at, freshness, confidence, confidence_ceiling,
                     causal_level, limitations[], contradictions[], status
Recommendation (in-request): + consequence_level, downside, reversibility,
                     expected_effect, how_to_test, rec_status
TrustOutput:
  claims                : list[Claim]
  recommendations       : list[Recommendation]
  evidence_status       : ok | MIXED_EVIDENCE | INSUFFICIENT_EVIDENCE
  overall_confidence    : int            # DERIVED (never the raw LLM number)
  downgrades            : list[{target, from, to, reason_code}]
  rejections            : list[{target, reason_code}]
  trust_record_id       : str            # correlation into ai_audit
```

### C4. Deterministic rules (binding)
1. **Confidence is server-derived; `final = min(derived, llm_proposed)`.** The
   server may only lower. Derivation = §7.2; ceilings `min(band_ceiling,
   type_ceiling)` = §7.3 (`FACT≤100, OBSERVATION≤85, INTERPRETATION≤70,
   HYPOTHESIS≤55`; bands `strong≤95, moderate≤75, weak≤55, insufficient→none`).
   `0 supporting evidence → 0`. Freshness can only decay. (Canonical: LLM 92,
   ceiling 65 → **65**.)
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

### C7. Done-definition for Phase 1
Pure functions + resolver implemented and unit-tested; adversarial trust tests
(§22) green; PG-gated resolver + shadow-record tests green on real Postgres;
read-only-agent / approval / belief / advisor suites unchanged; Ruff + Pyright
clean; no migration; protected files untouched.

---

## Decisions resolved in this revision

- **D1 — Claim persistence:** RESOLVED. No persistent `claims` table in Phase 1;
  DTOs + existing durable stores only (§3, C2). Future-table conditions documented.
- **D2 — Confidence is server-derived:** RESOLVED (model fixed). Full deterministic
  model + `final = min(derived, llm_proposed)` + per-band and per-claim-type
  ceilings + worked examples (§7, C4). *Remaining:* exact numeric constants per
  (band × type) need product sign-off (see open #2).
- **D3 — Causality:** RESOLVED (approach fixed). Evidence-level hierarchy
  (OBSERVATIONAL → RANDOMIZED), not a keyword filter; per-level allowed/forbidden
  language + scope guard (§9, C4.3). *Remaining:* the causal-basis catalogue
  (open #4).
- **D4 — Recommendation validation:** RESOLVED (approach fixed). Separate stage
  CLAIMS→EVIDENCE→INTERPRETATION→RECOMMENDATION→CONSEQUENCE/RISK→VALIDATION with
  statuses, plus the decision-intelligence principle (§12, C4.6).

## Open questions (still to decide before/within implementation)

1. **Confidence constants:** exact base/bonus/penalty values and the exact ceiling
   per (evidence band × claim type) — sign-off against CLAUDE.md bands (80/60/40).
2. **Enforcement vs advisory for the agent's prose answer:** at T3, do we *rewrite*
   the LLM answer to match the verified claims, or only annotate + override the
   structured fields and drop offending sentences? (Rewriting risks a second LLM
   pass; annotation is safer — leaning annotation.)
3. **Causal-basis catalogue:** which existing/future measurements count as each
   causal level? (Today: advisor outcomes = OBSERVATIONAL; creative-eval ≈
   QUASI-EXPERIMENTAL; none RANDOMIZED — so no RANDOMIZED-level language yet.)
4. **Metric registry coverage:** confirm the canonical calculators to wrap and
   which metrics are "calc-only" (CTR, conversion, ROAS, CAC, %-change, budget,
   experiment stats proposed).
5. **Shadow-mode duration (T2):** how long to run shadow comparison before
   enforcing, and the acceptance criterion (e.g. derived ≤ LLM confidence in N%
   of turns).
6. **Source tiers in UI:** when (which later phase) do VERIFIED/DERIVED/INFERRED/
   UNKNOWN badges appear, given this phase makes no UI change.

---

*This is an architecture + audit deliverable only. No Trust Layer code exists yet.
Review this plan before implementation begins.*
