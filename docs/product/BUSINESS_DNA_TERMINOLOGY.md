# Business DNA — Canonical Terminology & Component Map

**Status:** Stage 0 (Phase 7.20) — documentation standard. Approved for reference.
**Scope:** Establishes the one vocabulary the DM Tool intelligence architecture uses.
**Non-goal:** This document renames nothing in code, schemas, the database, or the
API. It is the dictionary that *future* stages rename *toward*. See
[`PHASE_7_20_STAGE_0_RECONCILIATION.md`](./PHASE_7_20_STAGE_0_RECONCILIATION.md)
for the migration-free correction plan.

> **Golden rule of this stage:** a term is either a **Data Store** (persists
> truth), a **Composition Service** (assembles truth into context, persists
> nothing new), or a **Consumer** (reasons over assembled context). These three
> are never interchangeable. Most of today's confusion comes from one word being
> used for all three.

---

## 1. The ten canonical terms

### 1. Business Profile — *Data Store*
The owner-declared and AI-analysed description of the business.
- **Lives in:** `business_profiles` table (`onboarding.BusinessProfile`), one row
  per user, tenant-scoped (`organization_id` + `brand_id`). The AI narrative is
  the `analysis` JSONB column (`BusinessAnalysis`, the "Intelligence Engine v2"
  fields), populated by `onboarding/analyzer.py`.
- **Holds:** name, website, industry, business type, target-audience *text*,
  products/services, USPs, free-text pricing, growth stage, budget/leads bands,
  goals, and the Brand Identity columns (below).
- **Is NOT:** evidence, beliefs, or a composition. It is the declared starting
  point everything else grounds against.

### 2. Brand Identity — *Concept (a slice of Business Profile)*
The visual + verbal signature every generation must stay on.
- **Lives in:** columns on `business_profiles` — `brand_colors`, `fonts`,
  `keywords`, `brand_rules`, `writing_style`, `brand_tone`.
- **Surfaced in UI as:** the `/brand-brain` route and completeness meter.
- **Is NOT:** a separate store, and **not** the `brands.Brand` row. `brands.Brand`
  is the *tenant boundary* (name, slug, logo, status) — the identity *content*
  lives on the profile.
- **UI-name note:** the product calls this surface "Brand Brain." That is a
  user-facing label, not a fifth system. Keep it; see §4 for the conflict it
  creates with "Business Brain."

### 3. Business Brain — *Data Store (evidence & research)*
The evidence-backed knowledge base built by research, **not** the profile.
- **Lives in:** the `business_brain` module — `brain_evidence` (typed claims),
  `brain_icps` (ICP hypotheses), `brain_research_jobs` (website/competitor/market
  research lifecycle). API prefix `/business-brain`.
- **Is NOT:** `advisor.brain.BusinessBrain`. That identically-named class is a
  **Business Profile projection** (see §4, conflict I1). When this document says
  "Business Brain" it always means the evidence/research store.

### 4. Marketing Brain — *Composition Service*
The read-only service that assembles the full picture for the reasoning surfaces.
- **Lives in:** `marketing_brain/service.py` → `build_context()` returning
  `MarketingBrainContext`, with `context_to_prompt_block()` for LLM injection and
  `marketing_brain/provenance.py` for the provenance legend.
- **Composes:** Business Profile + Business Brain evidence/ICP/research +
  analytics overview + advisor recommendations + outcomes + current strategy +
  learning insights — each kept in its own provenance tier.
- **Is NOT:** a store. It persists nothing. It is the closest thing today to the
  Business DNA read model and is the intended **base** for Stage 1.
- **UI-name note:** surfaced as "Marketing Brain" / the `/ai` agent surface.

### 5. Business DNA — *Concept (the future unified read model)*
The canonical, provenance-tagged, facet-structured view of everything known about
a business across all nine intelligence areas (Identity, Offer & Economics,
Audience/Customer, Market/Competitors, Positioning, Learned Beliefs, Performance).
- **Realised today by:** Marketing Brain composition (partially — it omits
  beliefs, brand identity, and economics). Stage 1 formalises it as a single
  `get_business_dna(brand)` read model that projects the existing stores.
- **Is NOT:** a new store, a new table, or a second Business Brain. It is a
  *projection standard*.
- **Collision warning:** "DNA" is already used in the `performance` module for
  **Creative DNA** (creative fingerprinting: `audience|concept|emotion|offer|
  funnel`). "Business DNA" is a distinct, higher-level concept. Never let code or
  copy blur the two; qualify with the full phrase.

### 6. Evidence — *Data (typed, provenance-bearing claims)*
A single claim about the business with a type and a source.
- **Canonical store:** `business_brain.BrainEvidence` — `kind ∈ {fact,
  observation, hypothesis, recommendation}`, `category ∈ {business, audience,
  market, marketing}`, `confidence` (server-set int), `status ∈ {active,
  superseded, contradicted}`, `claim_key`, and provenance (`source_url`,
  `source_type`, `snippet`, `discovered_at`).
- **Is NOT:** a belief. Beliefs *reference* evidence by id; they never copy it.

### 7. Beliefs — *Data Store (an evidence-graded graph)*
What the brand has **learned** — conclusions graded by the evidence behind them.
- **Lives in:** `beliefs` + `belief_evidence` (`belief` module). Confidence is
  **deterministically derived** from supporting/contradicting evidence
  (`belief/confidence.py`), decayed at read time by age (`belief/freshness.py`),
  and reconciled for contradiction/supersession (`belief/reconcile.py`).
  Formed server-side from *evaluated outcomes* (`belief/formation.py`) — no LLM
  writes a belief statement or its confidence.
- **Is NOT:** universal truth. A belief is a learned hypothesis/conclusion with a
  status and a confidence, nothing more.

### 8. Customer Intelligence — *Concept (a Business DNA facet)*
Who the customer is — hypothesised, measured, and actual, together.
- **Backed today by:** `business_brain.BrainIcp` (hypothesised ICP),
  `social.AudiencePattern` (measured engagement audience), and CRM/leads (actual
  people). These are **not** yet reconciled into one view — that reconciliation
  is the facet's job (Stage 4).
- **Is NOT:** a single store today; it is a facet to be composed.

### 9. Market Intelligence — *Concept (a Business DNA facet)*
Competitors and market signals.
- **Backed today by:** `business_brain` competitor/market research jobs → evidence
  (`brain_evidence`, categories `market`/`audience`) + the composed
  `CompetitorResearchResponse` / `MarketResearchResponse`.
- **Legacy duplicate:** the `competitors` module (one-shot LLM over free-text
  `profile.competitors`, no persistence, no grounding) — to be retired/folded
  (Stage 4). See conflict I6.
- **Capability limit:** research is local-only (own site + provided URLs + own
  evidence); there is no external market-sizing/discovery provider.

### 10. Business Economics — *Concept (a Business DNA facet; largely missing)*
Price points, margin, CAC, LTV, payback, budget, revenue targets, currency.
- **Backed today by (only):** free-text `pricing`, `monthly_budget_band`,
  `current_monthly_leads_band` on the profile, plus read-time metric computation
  in `trust/metrics.py` (CAC/ROAS/CPA from provider-verified inputs). There is no
  persistent unit-economics model.
- **Is NOT:** implemented as a facet yet. This is the single biggest capability
  gap (Stage 2).

---

## 2. Component classification (stores vs services vs consumers)

**The rule:** do not treat a composition service as a store, or a consumer as a
source of truth. Each row below is one, and only one, of the three.

### Data Stores (persist truth)
| Store | Canonical term it backs | Location |
|---|---|---|
| `business_profiles` (+ `analysis` JSONB) | Business Profile, Brand Identity | `onboarding/models.py` |
| `brain_evidence` | Evidence | `business_brain/models.py` |
| `brain_icps` (+ `brain_icp_evidence`) | Customer Intelligence (hypothesised) | `business_brain/models.py` |
| `brain_research_jobs` | Market Intelligence (research runs) | `business_brain/models.py` |
| `beliefs` (+ `belief_evidence`) | Beliefs | `belief/models.py` |
| `audience_patterns` / `winning_patterns` | Customer Intelligence (measured), Performance | `social/models.py` |
| `advisor_recommendations` / `_outcomes` / `_memory_events` | Advisor memory, outcomes | `advisor/models.py` |
| `learning_insights` | Learning (lessons) | `learning/` |
| `brands` | Tenant boundary (NOT Brand Identity content) | `brands/models.py` |

### Composition Services (assemble context; persist nothing new)
| Service | Produces | Consumed by | Location |
|---|---|---|---|
| `marketing_brain.build_context` | **Marketing Brain** (`MarketingBrainContext`) | agent, advisor | `marketing_brain/service.py` |
| `context.build_generation_context` | `GenerationContext` (+ `render_context_block`) | generators | `context/builder.py` |
| `advisor.signals.gather_intelligence_signals` | `IntelligenceSignals` | advisor recommendation engine | `advisor/signals.py` |
| `belief.grounding.resolve_evidence_grounding` | prompt block + `EvidenceGrounding` | coach, strategist, advisor, opportunities | `belief/grounding.py` |
| `belief.resolver` | resolved belief views (confidence + freshness) | grounding, agent beliefs | `belief/resolver.py` |
| `marketing_brain.provenance` | provenance legend/tiers | Marketing Brain prompt | `marketing_brain/provenance.py` |
| `trust.*` (T0–T3) | trust verdict + enforced output | agent turn | `trust/` |

> Note: three distinct composition services (Marketing Brain / GenerationContext /
> IntelligenceSignals) each pull an overlapping-but-different subset. Convergence
> onto one Business DNA read model is the goal of Stages 1 and 3 — **not** this
> stage.

### Consumers (reason over assembled context; never a source of truth)
| Consumer | Reads | Location |
|---|---|---|
| Generators (content, ads, visuals, campaigns, bundles) | `GenerationContext` | `*/service.py`, `*/prompts.py` |
| Autonomous agent | Marketing Brain + beliefs | `agent/runtime.py`, `agent/tools.py`, `agent/beliefs.py` |
| Advisor (recommendations) | `IntelligenceSignals` | `advisor/agent.py`, `advisor/service.py` |
| AI Coach | belief grounding | `coach/grounding.py` |
| Strategist | belief grounding | `strategist/grounding.py` |
| Opportunity engine | belief grounding | `opportunities/center.py` |
| Onboarding analyzer | *produces* `BusinessAnalysis` onto the profile | `onboarding/analyzer.py` |

---

## 3. Existing name → canonical term map

| Existing identifier / label (today) | Canonical term | Kind |
|---|---|---|
| `onboarding.BusinessProfile`, `business_profiles` | Business Profile | Store |
| `BusinessProfile.brand_colors/fonts/keywords/brand_rules/writing_style/brand_tone` | Brand Identity | Store (slice) |
| UI route `/brand-brain`, "Brand Brain" copy | Brand Identity (surface) | Consumer UI |
| `business_brain` module, `/business-brain` API, `BrainEvidence`, `BrainIcp`, `BrainResearchJob`, UI "Business Brain panel" | Business Brain (Evidence + Market/Customer research) | Store |
| `advisor.brain.BusinessBrain`, `/advisor/brain`, `BusinessBrainResponse`, `BusinessBrainUpdate`, `load_business_brain`, `brain_*` helpers | **Business Profile projection** (⚠ mis-named "Business Brain") | Service/Consumer |
| `marketing_brain` module, `MarketingBrainContext`, `/ai` "Marketing Brain" | Marketing Brain | Composition Service |
| `context.GenerationContext`, `render_context_block` | (generator composition — a Marketing-Brain-adjacent service) | Composition Service |
| `advisor.signals.IntelligenceSignals` | (advisor composition) | Composition Service |
| `belief.Belief`, `beliefs` | Beliefs | Store |
| `BrainEvidence` rows | Evidence | Store |
| `BrainIcp`, `social.AudiencePattern`, CRM/leads | Customer Intelligence | Facet (future) |
| `business_brain` competitor/market research, `competitors` module | Market Intelligence | Facet (future) |
| `pricing`, `monthly_budget_band`, `trust/metrics` CAC/ROAS | Business Economics | Facet (future, mostly missing) |
| `performance` "Creative DNA" | **Creative DNA** (unrelated) | Store/concept — keep separate from Business DNA |

---

## 4. The headline conflict (I1), stated once

Two different things are both called **"Business Brain"**:

1. **`advisor.brain.BusinessBrain`** + `GET/PATCH /api/v1/advisor/brain` +
   `BusinessBrainResponse`/`BusinessBrainUpdate` — a **projection of the Business
   Profile** (industry, audience, budget, completeness score). It stores nothing;
   it reshapes the profile for an editor and a completeness meter.
2. **The `business_brain` module** + `/business-brain` — the **Evidence &
   research store** (`BrainEvidence`, `BrainIcp`, `BrainResearchJob`).

They share a name, a UI home (the `/brand-brain` page renders the
`BusinessBrainPanel`, which calls `/business-brain`), and nothing else. Per this
stage's rules these identifiers and endpoints are **left unchanged**; the
canonical names and the deferred rename plan live in
[`PHASE_7_20_STAGE_0_RECONCILIATION.md`](./PHASE_7_20_STAGE_0_RECONCILIATION.md).

For provenance/confidence/freshness/contradiction vocabulary, see
[`PROVENANCE_STANDARD.md`](./PROVENANCE_STANDARD.md).
