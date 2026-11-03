# Provenance Standard — DM Tool Intelligence

**Status:** Stage 0 (Phase 7.20) — documentation standard. Approved for reference.
**Scope:** One provenance vocabulary, and how every existing confidence, freshness,
contradiction, and provenance mechanism maps into it.
**Non-goal:** No enum is created, renamed, or re-wired in this stage. The canonical
tier set below **already exists verbatim** in code as
`marketing_brain.provenance.ContextProvenance`; this document elevates it to the
single standard and maps the other vocabularies onto it.

---

## 1. The canonical provenance vocabulary (5 tiers)

These are the only public provenance tiers. They answer one question: **where did
this come from and how much should the reader trust it?** Taken verbatim from
`marketing_brain/provenance.py`:

| Tier | Meaning | Reader rule |
|---|---|---|
| **USER_STATED** | The owner told us (profile, brand voice, goals). | Authoritative about *intent*; not independently verified. |
| **SYSTEM_INFERRED** | The system derived it, not confirmed (observations, hypotheses, ICP, strategy, research candidates, learned beliefs). | Treat as a claim; never state as certain. |
| **VERIFIED** | Evidence-backed, confirmed-style claim (Business Brain `fact`, active). | Grounded; may be stated plainly. |
| **MEASURED** | Real first-party / provider-verified data (analytics KPIs, evaluated outcomes, verified metrics). | Grounded; never fabricate — if absent, say so. |
| **UNKNOWN** | An explicit gap. | Acknowledge and ask; never fill with a guess. |

**Two trust families:** USER_STATED and SYSTEM_INFERRED are *claims to verify*;
VERIFIED and MEASURED are *grounded*; UNKNOWN is a *gap*.

---

## 2. Confidence standard

**Confidence is never "the LLM sounded sure."** It is always one of:
- **server-derived** — a deterministic function of structured evidence
  (`belief/confidence.py`: base + per-support, experimental bonus, contradiction
  penalty, ceiling 95, never 100), or
- **measured** — read from real data (`trust/metrics.py`), or
- **absent** — then the surface shows INSUFFICIENT_EVIDENCE, not a guess.

Any LLM-emitted confidence is at most *clamped down* to the server value, never
trusted up. The Trust Layer (`trust/enforcement.py`, T3) enforces this on the
agent turn today; extending enforcement to every surface is a later stage.

**Display bands** (from the product constitution, `CLAUDE.md`): 80–100 High ·
60–79 Medium · 40–59 Low · <40 Speculative (do not ship as a CTA). These are a
*presentation* mapping over the numeric confidence, independent of provenance
tier.

---

## 3. Freshness standard

Confidence records evidence strength *when established*; freshness lowers it with
age at **read time**, never mutating the stored value (`belief/freshness.py`):

- **Fresh** (≤21d): no decay.
- **Aging** (21–180d): linear ramp.
- **Stale** (≥180d): floored (never loses more than 60%).

Guarantees: deterministic, bounded to `[floor, original]`, `0 → 0` (an
unvalidated belief is never aged *up*), monotonic with age, explainable.

**Known inconsistency (I5):** freshness decay is applied to **Beliefs only**.
`BrainEvidence` carries `discovered_at` but is **not** decayed by the composition
layers. The standard going forward: freshness is a property of *any* grounded
claim; applying the same read-time decay to Business Brain evidence is a future
correction (tracked in the reconciliation plan), not a Stage 0 change.

---

## 4. Contradiction standard

Contradictions are **surfaced, never silently dropped**, and are modelled as
relationships, never destructive edits:

- **Beliefs:** `belief/reconcile.py` supersedes the weaker/older belief on a
  *comparable* slice (scope match via distinguishing keys); history is retained.
  `belief/grounding.py` returns a `grounded` set **and** a `contradictions` set so
  a consumer can avoid acting on a conclusion newer outcomes undermined.
- **Evidence:** `BrainEvidence.status ∈ {superseded, contradicted}` with
  `superseded_by_id`; the Marketing Brain composition excludes these from the
  active set and reports the excluded count.
- **Trust:** `ReasonCode.CONFLICTING_EVIDENCE`, `ClaimStatus.MIXED`,
  `EvidenceStatus.MIXED_EVIDENCE`.

"Comparable slice" is defined identically in two pure modules
(`trust/contracts.scopes_comparable` and belief reconcile) via a shared set of
distinguishing scope keys (channel, platform, audience, segment, metric, window,
…). Keep these two definitions in lock-step; a future correction consolidates the
key set in one place.

---

## 5. Mapping existing mechanisms → canonical tiers

### 5.1 Business Profile & Brand Identity
| Source | Tier |
|---|---|
| Profile fields the owner entered (name, industry, audience text, goals, pricing text, bands) | **USER_STATED** |
| Brand Identity (colors, fonts, keywords, rules, writing style, tone) | **USER_STATED** |
| `BusinessAnalysis` (AI "Intelligence Engine v2" narrative) | **SYSTEM_INFERRED** |

### 5.2 Business Brain evidence (`BrainEvidence.kind`, status `active`)
| Kind | Tier |
|---|---|
| `fact` | **VERIFIED** |
| `observation` | **SYSTEM_INFERRED** (a seen signal, not a conclusion) |
| `hypothesis` | **SYSTEM_INFERRED** |
| `recommendation` | **SYSTEM_INFERRED** |
| any kind with status `superseded`/`contradicted` | excluded from active context; shown as history / contradiction, not as a current tier |

ICP hypotheses (`BrainIcp`, status `hypothesis`/`accepted`), competitor
candidates, and market signals (research) are all **SYSTEM_INFERRED** — "accepted"
is a workflow state, not independent verification.

### 5.3 Beliefs
A belief is a **learned conclusion**, so its public tier is **SYSTEM_INFERRED**,
*annotated with the strength of its evidence*:
| Belief evidence basis | Annotation |
|---|---|
| supported by an experimental ref (`advisor_outcome`, see `EXPERIMENTAL_REF_KINDS`) | basis is **MEASURED** → higher server confidence |
| supported only by observational refs / `brain_evidence` | basis is **SYSTEM_INFERRED / VERIFIED** per the underlying evidence |
| `status = contradicted` | surfaced in the contradictions set, not as grounding |
| `status = unvalidated` (0 confidence) | **UNKNOWN** / INSUFFICIENT_EVIDENCE |

The conclusion never claims **VERIFIED**; the evidence *behind* it may be MEASURED.
Provenance surfaces should show both ("learned conclusion, grounded in measured
outcomes").

### 5.4 Measured data
| Source | Tier |
|---|---|
| Analytics KPIs (leads, conversion, views) | **MEASURED** |
| Evaluated advisor outcomes (effectiveness scores) | **MEASURED** |
| Provider-verified monetary metrics (spend, revenue, ROAS, CAC via `trust/metrics`) | **MEASURED** |

### 5.5 Gaps
| Source | Tier |
|---|---|
| Marketing Brain / Business Brain `unknown` list | **UNKNOWN** |
| Missing profile, absent strategy, no validated beliefs | **UNKNOWN** |
| `EvidenceStatus.INSUFFICIENT_EVIDENCE`, `EvidenceBand.INSUFFICIENT` | **UNKNOWN** |

---

## 6. Trust Layer enum crosswalk

The Trust Layer (`trust/enums.py`) is finer-grained than the 5 tiers *by design*
(it drives enforcement, not display). Public provenance maps as:

| Trust `SourceTier` | Canonical tier |
|---|---|
| `USER_PROVIDED` | USER_STATED |
| `VERIFIED_PROVIDER`, `FIRST_PARTY_DATA` | MEASURED |
| `RESEARCH`, `DERIVED_INTERNAL`, `MODEL_INFERENCE` | SYSTEM_INFERRED |
| `UNKNOWN` | UNKNOWN |

| Trust concept | Relation to canonical tiers |
|---|---|
| `ClaimType` ladder (fact→observation→interpretation→hypothesis→recommendation) | `fact` ⇒ eligible for VERIFIED; all lower ⇒ SYSTEM_INFERRED. The ladder may only be *demoted*. |
| `EvidenceBand` (strong/moderate/weak/insufficient) | strength *within* a tier; `insufficient` ⇒ UNKNOWN. |
| `EvidenceStatus` / `ClaimStatus` (`insufficient`/`mixed`) | UNKNOWN / contradiction surfacing. |
| `CausalLevel` | orthogonal — governs causal wording, not the provenance tier. |

**Reconciliation principle:** the four vocabularies
(`BrainEvidence.kind` · `BeliefStatus`+derived confidence · `ContextProvenance`
tiers · Trust enums) are **not merged**. `ContextProvenance` is the single
*public* tier; the others remain as internal detail and map *up* to it via the
tables above. This keeps enforcement precise while giving every surface (and the
UI) one honest label set.

See [`BUSINESS_DNA_TERMINOLOGY.md`](./BUSINESS_DNA_TERMINOLOGY.md) for the terms and
[`PHASE_7_20_STAGE_0_RECONCILIATION.md`](./PHASE_7_20_STAGE_0_RECONCILIATION.md) for
the deferred corrections and Stage 1 prerequisites.
