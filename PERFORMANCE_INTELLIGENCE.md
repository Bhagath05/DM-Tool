# PERFORMANCE INTELLIGENCE ENGINE — Phase 9 Design

> Status: **Design only.** No code. No migrations. No PRs.
> Constitution: still frozen. Every output of this engine must obey
> the AI Recommendation Contract (recommendation + reason + confidence
> + expected_result), Business Impact First, 3-Question Screen Test,
> and Ship-Questions-Not-Numbers from `CLAUDE.md`.

---

## 1. Executive Summary

### What it does
A closed-loop system that:

1. **Pulls** raw performance data from ad platforms, CRM, sales,
   bookings, calls, WhatsApp and the founder's own landing pages.
2. **Diagnoses** what happened, why, and what it cost the business.
3. **Recommends** the next action in plain founder language
   (BusinessMetric / AiRecommendation cards we already ship).
4. **Tests** recommendations through structured experiments.
5. **Learns** — per-brand and per-industry — and feeds winners back
   into the Creative Engine and the AI Coach.

### Why it exists
Today DM Tool **makes** assets. It does not yet **know** whether
those assets earned money. Without that loop:

- Every creative is generated cold, with no prior on what works for
  this brand.
- The AI Coach can only see funnel structure, not outcomes.
- The founder cannot answer "what should I do with my next ₹10k?"
- The system cannot compound — it forgets every campaign the day
  after it runs.

### Business problems solved
| Founder question today | Engine answers |
|---|---|
| "Is my ad working?" | Yes/No + why + how confident |
| "Which creative is winning?" | Top creative + the feature that's driving it |
| "Where should I put my next ₹10k?" | One ranked recommendation with expected lift |
| "Why did my CPL go up this week?" | Ranked causes with evidence |
| "Should I scale, kill, or refresh?" | Decision with guardrails |
| "What works for restaurants like me?" | Anonymised industry patterns |

This is the wedge from **AI Creative Generator** to
**AI Performance Marketing Operating System**.

---

## 2. System Architecture

### Data flow
```
[Ad Platforms]   [CRM]   [Sales]   [Bookings]   [Calls]   [WhatsApp]   [Web]
       \           \        \          \           |          /          /
        \           \        \          \          |         /          /
         +-----+-----+-----+-----+-----+-----+-----+--------+----------+
                                   |
                          (1) Connector Layer
                                   |
                          (2) Normaliser  ----> raw events store
                                   |
                          (3) Rollup Engine (campaign / creative /
                                              audience / offer / day)
                                   |
                +------------------+------------------+
                |                                     |
        (4) Diagnostics                       (5) Experimentation
        (rules + anomalies +                  (hypothesis / variant /
         constrained LLM)                      decision rule)
                |                                     |
                +------------------+------------------+
                                   |
                          (6) Recommendation Composer
                          (enforces Constitution contract)
                                   |
                +------------------+------------------+
                |                                     |
        (7) Founder Surfaces                  (8) Learning Memory
        (Dashboard / Coach /                   (tenant + industry,
         Alerts — BusinessMetric /             writes back into
         AiRecommendation only)                Creative Engine prior)
```

### Components & service boundaries
| Component | Owns | Reuses |
|---|---|---|
| Connector Layer | Auth + pull from Meta/Google/CRM/etc | existing tenant/brand model, `secrets` |
| Normaliser | Schema-stable event ingestion | existing SQLAlchemy + Alembic |
| Rollup Engine | Pre-aggregated cubes for hot reads | postgres window funcs; arq worker |
| Diagnostics | Deterministic rules + LLM narrative | `analytics-translator` confidence bands |
| Experimentation | Tests, variants, decisions | new |
| Recommendation Composer | Contract enforcement | Pydantic + existing Coach contract |
| Founder Surfaces | UI | `<BusinessMetric>`, `<AiRecommendation>`, `<ComingSoonCard>`, `view-mode` |
| Learning Memory | tenant + industry patterns | new |

### Dependencies
- **Reuses**: `coach` module (action schema), `analytics-translator`
  pattern, `trends-translator` pattern, `view-mode`, multi-tenant
  middleware, Constitution-shaped UI cards. No new UI primitives.
- **New external**: Meta Marketing API, Google Ads API, plus first-class
  CSV upload path so we can ship value before connectors land.
- **Internal new**: `aicmo/modules/performance/` (mirrors coach module
  layout — schemas / repository / service / router / prompts).

### Service boundary — explicit non-goals
- This engine **does not** replace the Creative Engine; it feeds it.
- It **does not** replace the AI Coach; it gives the Coach more
  signal and may post structured recommendations into the Coach feed.
- It **does not** ship a generic analytics product. Per Constitution,
  analytics is never the front door.

---

## 3. Data Sources

### Tiering
- **Tier A** = required to ship Phase 9.1 (single-platform value).
- **Tier B** = required to ship full diagnostics.
- **Tier C** = unlocks autonomous optimisation.

### Meta Ads (Tier A first)
**Required** (per ad / per day):
`account_id, campaign_id, adset_id, ad_id, date, impressions, clicks,
spend, conversions, conversion_value, currency, objective`

**Optional / breakdowns**:
`frequency, reach, ctr, cpc, cpm, video_p25/p50/p75/p100,
demographic (age, gender, geo), placement, device`

### Google Ads (Tier B)
Same shape — `customer_id, campaign_id, ad_group_id, ad_id, date,
impressions, clicks, cost_micros, conversions, conversion_value,
search_terms (opt), device, geo`.

### CRM / Lead DB (Tier A — already in our DB)
`lead_id, brand_id, source_campaign_id, source_ad_id, utm_*,
created_at, status, qualified_at, value`

### Sales / Orders (Tier B)
`order_id, lead_id (FK), brand_id, amount, currency, created_at,
channel`. Required to compute ROAS. Without this we can only ship
CPL — not CAC, not LTV.

### Bookings (Tier B, vertical-specific)
`booking_id, lead_id, brand_id, slot_at, status, value`.

### Call Tracking (Tier C)
`call_id, source_campaign_id, duration_sec, recording_url (opt),
outcome (booked / qualified / spam)`. Vendor: CallRail / Exotel.

### WhatsApp (Tier C)
`conversation_id, brand_id, source, started_at, qualified_flag,
agent_disposition`.

### Web Analytics (Tier B)
`session_id, page_path, utm_*, landing_at, conversion_event,
conversion_value`. GA4 / Plausible / our own.

### Landing pages (Tier A — already ours)
`page_id, views, submissions, time_on_page_sec, scroll_depth`.

### Creative performance (Tier A)
`creative_id` joins back to the asset we generated, plus the **tags
applied at generation time**: `concept_family, emotion, audience_id,
platform, funnel_stage, business_goal, offer_type`. These tags are
how we attribute outcome back to creative choice.

> Tagging discipline at generation time is the single biggest
> investment that makes this engine work. Without it the rollups
> degenerate into "ad_123 won" with no transferable feature.

---

## 4. Performance Diagnostics Engine

### Question contract
Every diagnostic must answer four questions in one record:
1. **What happened?** (observation — factual, from rollups)
2. **Why did it happen?** (hypothesised cause — ranked, with evidence)
3. **What is the business impact?** (in money / leads / time)
4. **What should be done next?** (recommendation with expected_result)

This is the Constitution's `AiRecommendation` shape, period.

### Three-layer engine
| Layer | Job | Output confidence ceiling |
|---|---|---|
| **L1 — Deterministic rules** | "CTR down >25% w/w on 7d window, frequency >3.0" | 90 |
| **L2 — Anomaly detection** | Z-score vs trailing 28d baseline, with min-sample gate | 80 |
| **L3 — LLM narrative** | Compose plain-English cause + recommendation from L1+L2 evidence | 75 |

**Rule:** L3 may never run without at least one L1 or L2 trigger.
The LLM never speculates — it explains. This mirrors what we did
for the Coach (Phase 1).

### Worked example
| Observation | Cause hypothesis | Evidence | Recommendation |
|---|---|---|---|
| CTR fell from 1.8% → 0.9% over last 7d on ad_123 | Creative fatigue | frequency up 2.1→3.7; CPM stable; same audience | Refresh creative — clone winning concept family with new hook |
| | Audience saturation | reach plateau 92% of saved audience | Duplicate ad into lookalike-2% |
| | Weak hook | thumb-stop rate (3s view / impression) down 18% | A/B test new first frame |

The card the founder sees:
- whatIsHappening: "Your top ad is tiring — clicks down 50% this week."
- impactCategory: lead
- recommendation: "Refresh the creative with a new hook."
- expectedResult: "Fresh creative usually recovers 60-80% of the lost CTR within 5-7 days."
- confidence: 80 (anomaly + rule both fire)
- reason: "Frequency rose from 2.1 to 3.7 — same people are seeing it 4x; click-rate dropped from 1.8% to 0.9%."
- technicalDetails: raw numbers, available in Pro mode.

### Small-sample discipline (Constitution)
Each rule has a `min_sample` (impressions / conversions / spend).
Below threshold → diagnostic is suppressed and the slot renders a
`<ComingSoonCard>` ("not enough data yet to be useful"). No fabrication.

---

## 5. Creative Performance Engine

### Tag-first attribution
The Creative Engine **already** knows the concept_family, emotion,
audience, platform, funnel_stage, business_goal at generation time.
We persist those tags on the creative record and join to performance
events through `creative_id`.

### Rollup grain
Daily rollups per `(creative_id, date)` and aggregate cubes per
`(brand_id, dim, dim_value, window)` where `dim ∈ {concept_family,
emotion, audience, platform, funnel_stage, business_goal, offer_type}`.

### Decision rules
- **Winner** = top-quartile CVR/ROAS in its cube, p<0.05 vs cube
  median, min_sample met.
- **Loser** = bottom-quartile + min_sample met + ROAS < target.
- **Trend** = 7d slope of CVR / ROAS, only surfaced when |slope| beats
  noise floor (Mann-Kendall test or simple sign test).

### Outputs
- "Family-emotion combinations that won this month" → feeds
  Creative Engine prior.
- "Concept family X has lost twice in a row" → suppress in
  recommendations.
- "Creative ad_123 is on a run — duplicate into new audience" →
  recommendation card.

---

## 6. Audience Intelligence Engine

### Signals
- Conversion-weighted ROAS per audience (with sample gate).
- Frequency curve per audience (fatigue detector).
- Early-signal score for new audiences (CTR + add-to-CRM rate in
  first 1k impressions; explicitly confidence-capped at 60).
- Cost-per-conversion variance (volatile audiences flagged).

### Outputs
| Card | Trigger |
|---|---|
| Best audience | Top ROAS, sample met, stable trend |
| Worst audience | Bottom ROAS over 28d + budget > 10% of spend |
| Emerging audience | New audience hitting median ROAS within first 7d |
| Audience fatigue | Frequency >3 AND CTR down >25% on 14d |
| Budget opportunity | Audience ROAS above target with budget headroom |

### Constitution alignment
Audience cards are AiRecommendation only — never raw "Audience 7
performed 23% better." Always plain language: *"Families convert
3x better than young adults. Move ₹5k from young-adults to families
next week — expected: ~12 more bookings."*

---

## 7. Offer Intelligence Engine

### Inputs
Offer type is a tag on every campaign at creation time:
`discount | free_trial | consultation | bundle | promotion | seasonal | none`.

### Comparison
- Conversion rate by offer.
- Average order value / booking value by offer.
- 30-day retention (where data exists) — guards against "discount
  always wins on top of funnel but loses on LTV".

### Decision rule
Recommend swap when one offer beats another by ≥1.3x conversion AND
sample is met AND LTV is not materially worse.

### Output
*"Free consultation books 2x more calls than '20% off'. Try free
consultation on your next campaign — expected ~15 extra bookings
per ₹10k spent."*

---

## 8. Budget Optimisation Engine

### Decision matrix
| ROAS vs target | Trend (7d) | Sample | Action |
|---|---|---|---|
| Above | Rising | Met | **Scale aggressive** (+30%) |
| Above | Flat | Met | **Scale steady** (+15%) |
| Above | Falling | Met | **Hold** + investigate (likely fatigue) |
| At | Flat | Met | **Hold** |
| Below | Rising | Met | **Hold** + monitor |
| Below | Flat / falling | Met | **Pause** |
| Any | Any | Not met | **Hold** + Coming Soon card |
| New (≤7d) | — | — | **Learn** — no action, gather sample |

### Guardrails
- Never auto-scale > +30% in 24h (Meta retraining shock).
- Never auto-pause without N≥conversions_required for that vertical.
- Always show the founder the recommendation **before** auto-apply
  (Phase 9.1–9.3 are advisory only; Phase 9.5+ adds one-click apply).

### Reuse
Decision output flows through the same Recommendation Composer →
becomes an `AiRecommendation` card on the dashboard and (when high
confidence) an action in the AI Coach weekly list.

---

## 9. Experimentation Engine

### Test schema
```
Experiment {
  id, brand_id, hypothesis (plain English),
  surface (creative | audience | offer | landing_page | headline),
  variants: [Variant{id, payload, traffic_split}],
  success_metric (CTR | CVR | CPL | ROAS | bookings),
  min_sample (per variant),
  expected_lift (founder-facing range),
  decision_rule (Bayesian or frequentist threshold),
  status (draft | running | decided | aborted),
  winner_variant_id?,
}
```

### Lifecycle
1. **Propose** — Diagnostics or founder seeds a hypothesis.
2. **Run** — Variants ship; rollup engine tags events with variant_id.
3. **Monitor** — Dashboard widget shows progress to min_sample.
4. **Decide** — Auto-decide when min_sample met AND threshold passed.
   Otherwise auto-abort at hard cap (e.g. 21 days, ₹20k).
5. **Extract** — Winner feeds Winner Extraction Engine (§10).

### Defaults shipped on day 1
- Headline test (3 variants) for any landing page above sample floor.
- Creative concept-family test once a brand has ≥2 family options.
- Offer test (discount vs free-trial vs consult).

### Honest-uncertainty rule
If a test ends inconclusive → say so. No "trending positive" cope.
The founder card says *"No clear winner yet — needs 2 more weeks
or +₹3k spend to decide."*

---

## 10. Winner Extraction Engine

When a test decides a winner OR when a creative hits "winner" status
in the Creative Performance Engine:

1. Extract feature vector:
   `{audience, emotion, offer, hook_text, funnel_stage,
     visual_style, platform, time_of_day}`
2. Score features by marginal contribution (lightweight regression
   over recent decided experiments).
3. Write to `winner_patterns` (tenant) and conditionally to
   `industry_learning` (cross-tenant, anonymised, k>=10).
4. Feed back into:
   - **Creative Engine prior** — bias new generations toward winning
     features.
   - **AI Coach** — surface as a "what's working" insight.
   - **Recommendation queue** — "generate 3 variants of this winner
     for new audiences."

---

## 11. Learning Memory

### Two tiers
| Tier | Scope | Storage | Use |
|---|---|---|---|
| **Tenant memory** | Per brand | full granular | Bias this brand's future recommendations |
| **Industry memory** | Anonymised cross-brand | aggregated signatures | Bias new brands (cold start) |

### Storage model — `industry_learning`
```
id, industry, pattern_type, signature (jsonb),
evidence_count, brand_count, confidence,
first_seen, last_seen, last_validated
```

`signature` is the structural feature (e.g.
`{concept_family: "family_experience", emotion: "warmth",
audience_pattern: "parents_25_45"}`), never raw creative.

### k-anonymity floor
A pattern is only **read** by other tenants if `brand_count ≥ 10`.
Below that it's tenant-only. Prevents leaking individual brand
strategy.

### Decay & retention
| Data | Retention |
|---|---|
| Raw events | 90 days hot, 12 months cold |
| Daily rollups | 24 months |
| Diagnostics / recommendations | indefinite (small) |
| Tenant winners | indefinite |
| Industry patterns | indefinite, but `last_validated` re-scored monthly; patterns that stop replicating lose confidence |

### Examples (illustrative — actual patterns are learned)
- *Restaurants:* family-experience creatives outperform food-only
  creatives in dinner-time campaigns.
- *Gyms:* transformation creatives outperform authority creatives
  for cold audiences; reverse for warm.
- *Real estate:* video walk-throughs beat carousels for high-ticket
  listings; carousels win for budget listings.

These start as hypotheses, become evidence-backed patterns, and
flow into the Creative Engine as priors.

---

## 12. Founder Dashboard

### Hard rule
Every widget renders through **existing components only**:
`<BusinessMetric>`, `<AiRecommendation>`, `<ComingSoonCard>`,
governed by `view-mode` (Simple default, Pro opt-in). No new
primitives. No charts on Simple mode.

### Proposed widgets (Simple mode)
| Widget | Component | Says |
|---|---|---|
| What's working | AiRecommendation | "Family ad #2 is your winner — book more like it." |
| What's broken | BusinessMetric (bad) | "Instagram CPL doubled this week." |
| Next ₹10k | AiRecommendation | "Move ₹10k from young-adults to families." |
| Audience to test next | AiRecommendation | "Test parents aged 35-45 — looks promising." |
| Spend gauge | BusinessMetric | "You've spent ₹38k of ₹50k this month — on track." |
| Coming Soon slots | ComingSoonCard | Honest empty states for any category lacking sample. |

### Pro mode adds
- Inline technical details (already supported by Phase 2).
- Diagnostic evidence panel (the raw rule + numbers that fired).
- Experiment progress with confidence intervals.

### Founder language test
Before shipping any string:
- "Would my mom understand this?" If no → rewrite.
- Replace every metric noun with a verb the founder can take.
- Currency follows account currency, never hardcoded.

---

## 13. API Architecture

### New module
`apps/api/aicmo/modules/performance/`
Mirrors the `coach` module: `schemas.py / repository.py / service.py /
router.py / prompts.py / jobs.py`.

### Endpoints (v1)
| Method | Path | Purpose |
|---|---|---|
| GET | `/performance/connectors` | List ad accounts connected |
| POST | `/performance/connectors/meta` | OAuth connect Meta |
| DELETE | `/performance/connectors/{id}` | Disconnect |
| POST | `/performance/sync` | Trigger pull (admin / debug) |
| GET | `/performance/overview` | Founder dashboard payload (cards) |
| GET | `/performance/diagnostics` | Open diagnostic recommendations |
| POST | `/performance/diagnostics/{id}/dismiss` | Founder dismisses |
| POST | `/performance/diagnostics/{id}/apply` | Mark acted-upon (manual) |
| POST | `/performance/experiments` | Create test |
| GET | `/performance/experiments/{id}` | Status |
| GET | `/performance/learning` | Tenant + applicable industry patterns |
| POST | `/performance/upload-csv` | Phase 9.1 wedge — manual ingest |

All multi-tenant via existing `X-Organization-Id` + `X-Brand-Id`
headers. AuthZ via existing role middleware.

### Background jobs (arq)
| Job | Cadence | Purpose |
|---|---|---|
| `performance.pull` | every 30 min | Pull from connected platforms |
| `performance.rollup` | hourly | Refresh daily cubes |
| `performance.diagnose` | hourly | Run L1 + L2; queue L3 |
| `performance.experiment_tick` | hourly | Check experiment decision rules |
| `performance.learning_consolidate` | nightly | Refresh tenant + industry memory |
| `performance.connector_health` | every 15 min | Detect breakage; alert |

### Caching
Redis: hot dashboard payload (TTL 5 min, invalidated on rollup).
No caching on diagnostics — they must reflect latest data.

### Storage
Postgres for everything (we already have it). No new datastore until
volumes prove the need. Cold storage of raw events → S3/Backblaze after
90 days only if needed (defer).

### Analytics pipelines
Use SQL window functions + materialised views before reaching for
dbt / Snowflake / etc. Resist building data infra until rollups
break Postgres.

---

## 14. Database Design

### New tables (key columns only)

#### `ad_accounts`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| brand_id | uuid FK | indexed |
| platform | enum(meta, google, linkedin, tiktok) | |
| external_account_id | text | |
| display_name | text | |
| status | enum(connected, broken, paused) | |
| connected_at, last_synced_at | timestamptz | |
| secret_ref | text | pointer to secret store, never plaintext |

#### `ad_creatives`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| brand_id | uuid FK | |
| source_asset_id | uuid FK | links to our generated asset |
| platform, external_creative_id | text | |
| tags | jsonb | concept_family / emotion / audience / funnel_stage / business_goal / offer_type |
| created_at | timestamptz | |
Indexes: `(brand_id, platform, external_creative_id)`, GIN on `tags`.

#### `performance_events`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| brand_id | uuid FK | indexed |
| platform | enum | |
| entity_type | enum(campaign, adset, ad) | |
| entity_id | text | |
| date | date | partition key |
| impressions, clicks, conversions | bigint | |
| spend_micros, conversion_value_micros | bigint | currency-agnostic int |
| currency | text(3) | |
| raw | jsonb | optional, debug only |
Partition: `RANGE (date)` monthly. Indexes:
`(brand_id, entity_type, entity_id, date)`.

#### `campaign_results` / `creative_results` / `audience_results` / `offer_results`
Rollup cubes. Same shape:
| col | notes |
|---|---|
| brand_id, dim_value, date | composite key |
| impressions, clicks, conversions, spend, conversion_value, ctr, cvr, cpl, roas | |
| sample_state | enum(insufficient, sufficient) — pre-computed |

Materialised views OR plain tables refreshed by rollup job. Start
with plain tables (simpler ops); promote to MV only if reads suffer.

#### `diagnostics`
| col | notes |
|---|---|
| id, brand_id | |
| kind | text (rule id) |
| observation, hypothesised_cause, business_impact, recommendation | text |
| expected_result, reason | text |
| confidence | int 0-100 |
| evidence_refs | jsonb (event/rollup ids that fired the rule) |
| status | enum(open, acted_on, dismissed, expired) |
| created_at, resolved_at | timestamptz |
Index: `(brand_id, status, confidence desc, created_at desc)`.

#### `experiments`
| col | notes |
|---|---|
| id, brand_id | |
| hypothesis, surface, success_metric | text/enum |
| variants | jsonb |
| min_sample, expected_lift | numeric |
| decision_rule | jsonb |
| status, winner_variant_id | |
| started_at, ended_at | |

#### `winner_patterns`
| col | notes |
|---|---|
| id, brand_id | |
| source_experiment_id (nullable) | |
| features | jsonb |
| evidence_count, confidence | |
| last_seen | |

#### `industry_learning`
| col | notes |
|---|---|
| id | uuid PK |
| industry | text indexed |
| pattern_type | enum(creative, audience, offer, channel, budget) |
| signature | jsonb (anonymised feature combination) |
| evidence_count, brand_count, confidence | |
| first_seen, last_seen, last_validated | |
Index: `(industry, pattern_type, confidence desc)`.

### Relationships
```
brands 1—n ad_accounts 1—n ad_creatives 1—n performance_events
brands 1—n diagnostics
brands 1—n experiments 1—n winner_patterns
industries 1—n industry_learning
```

### Index discipline
Every table that the dashboard reads from must have a composite
index that starts with `brand_id` — multi-tenant query path is
non-negotiable.

---

## 15. Automation Opportunities

### Maturity ladder
1. **Observe** (Phase 9.1) — read-only, surface in UI.
2. **Recommend** (Phase 9.2) — Constitution-compliant cards, no
   platform writes.
3. **Semi-auto** (Phase 9.3+) — one-click apply with confirmation:
   pause ad, shift budget, duplicate creative.
4. **Autonomous within guardrails** (Phase 9.5+) — only for
   high-confidence (≥85), low-blast-radius actions (budget shifts
   within ±20%, never pausing a winner, daily spend cap).

### Per-platform readiness
| Platform | API quality | Order |
|---|---|---|
| Meta | Mature, well-documented | First |
| Google Ads | Mature, but quota-heavy | Second |
| LinkedIn | Mid | Third |
| TikTok | Improving | Fourth |
| WhatsApp Ads | Via Meta | Comes free with Meta |

### Safety invariants (must hold at every level)
- Founder can always disable autonomy with one toggle.
- Every autonomous action emits an `AiRecommendation`-shaped audit
  card after the fact ("I moved ₹3k from A to B because…").
- Daily change budget capped per brand.
- Never act if connector health is degraded.

---

## 16. Risk Analysis

| Risk | Mitigation |
|---|---|
| **Attribution gaps** (iOS 14+, cross-device, organic mix) | Multi-touch attribution lite + last-touch fallback + survey question on lead form; always disclose attribution confidence in `reason`. |
| **Small samples** producing noisy diagnostics | Hard `min_sample` gates per rule. Below threshold → Coming Soon card. (Same pattern as Phase 3.) |
| **Bad LLM narratives** | LLM is explainer not detective — never runs without L1/L2 trigger. Confidence cap 75 for LLM-only language. |
| **Connector breakage** silently degrading data | `performance.connector_health` job + visible "data is stale" banner; suppress affected recommendations. |
| **Tenant leakage via industry memory** | k-anonymity floor (`brand_count ≥ 10`), signatures only (no raw creative), opt-out flag per brand. |
| **Over-trusting recent days** (weekend swings, holidays) | 28d baseline + significance test; weekday/seasonal smoothing where possible. |
| **Optimizer death-spiral** (pause winners on noise, then no data) | Never pause without N events; never resume without manual; daily change cap. |
| **Recommendation overload** | Top-N per surface, dedup, dismiss memory. Founder sees ≤3 actions at a time. |
| **Currency / locale bugs** | Store in `*_micros` + `currency`; render via account currency only (Constitution rule). |
| **Compliance / PII** in raw events | Pull aggregated only where possible; if individual data lands (CRM), reuse existing tenant data-handling. No PII into industry memory. |
| **Cost of LLM calls scaling** | LLM only at composer / nightly consolidation, not per row. Prompt cache as we already do. |
| **Founder dismisses everything** (signal of bad recommendations) | Dismiss-rate is a first-class metric; recommendation kinds with >50% dismiss rate auto-suppressed pending review. |

---

## 17. Implementation Roadmap

> Reuse-first. Each phase is independently shippable and Constitution-compliant.

### Phase 9.1 — Read-only Wedge (smallest production-ready)
**Scope:** Manual CSV upload (Meta Ads Manager export) + creative
tagging + 1 rollup cube + 1 diagnostic ("which creative is winning")
+ 1 recommendation ("where to put next ₹10k"). Surface on existing
dashboard via `<AiRecommendation>` cards.

- **Files:** new `apps/api/aicmo/modules/performance/` (schemas, repo,
  service, router); new migration for `ad_creatives`,
  `performance_events`, `creative_results`, `diagnostics`; new
  `apps/web/src/lib/performance-translator.ts`; new
  `apps/web/src/app/(app)/dashboard/_components/whats-working.tsx`
  (uses existing `<AiRecommendation>`).
- **Risk:** low — no external API, no autonomy.
- **Tests:** translator unit tests (Constitution contract,
  small-sample suppression); ingest happy-path; one e2e from upload
  to card render.
- **Outcome:** founder uploads yesterday's Meta export, sees a
  Constitution-shaped "what's working / where to put next ₹10k"
  card. Demonstrable end-to-end value before connector work.

### Phase 9.2 — Meta Connector + Full Diagnostics
**Scope:** Meta OAuth, scheduled pull, full L1+L2 diagnostics across
creative / audience / offer / budget, dashboard widgets.

- **Files:** `connectors/meta.py`, `jobs.py`, new rollup tables,
  diagnostic rules registry, dashboard widget components.
- **Risk:** medium — external API quotas, OAuth, secret storage.
- **Tests:** connector contract tests against Meta sandbox;
  rule-engine unit tests with fixture rollups; integration tests
  for diagnostics queue.
- **Outcome:** zero-touch daily diagnostics for any brand with a
  connected Meta account.

### Phase 9.3 — Experimentation + Winner Extraction
**Scope:** experiments table, lifecycle, default tests (headline,
creative family, offer), winner extraction into `winner_patterns`,
Coach integration.

- **Files:** `experiments/` submodule, `winner-extractor.py`, Coach
  feed integration, new `<ExperimentProgress>` widget.
- **Risk:** medium — statistical correctness must be auditable.
- **Tests:** decision-rule unit tests (frequentist + Bayesian); fake
  experiment fixtures end-to-end.
- **Outcome:** founders can run structured tests; winners auto-feed
  the Creative Engine.

### Phase 9.4 — Industry Learning Memory
**Scope:** `industry_learning` table, anonymisation pipeline,
k-anonymity enforcement, read-path into recommendations for cold-start
brands.

- **Files:** `learning/` submodule, anonymiser, consolidation job.
- **Risk:** medium-high — tenant-leakage risk; needs a security review
  before any cross-tenant read path opens.
- **Tests:** k-anonymity floor invariant tests; redaction tests;
  opt-out enforcement tests.
- **Outcome:** new brands see useful industry patterns from day 1.

### Phase 9.5 — Semi-Autonomous Optimisation
**Scope:** one-click apply (pause, scale ±, duplicate); audit cards;
guardrails; per-brand autonomy toggle.

- **Risk:** high — first time we mutate the platform on behalf of
  the founder. Must ship behind explicit opt-in + daily change cap.
- **Tests:** dry-run + real-run parity tests against Meta sandbox;
  guardrail invariant tests; audit-trail completeness.
- **Outcome:** the system stops being advisory and starts driving
  outcomes.

---

## 18. Final Recommendation

### Smallest production-ready version
**Phase 9.1 only.** Manual CSV upload + creative tagging + one
diagnostic + one recommendation. No connector, no automation, no
industry memory. Ship in a single 1-week iteration.

### What to build first (this week, if approved)
1. `ad_creatives` table + back-fill tags from existing generation
   metadata. *This is the single biggest unlock — without tags, the
   rest of the engine is blind.*
2. CSV ingest endpoint + parser for Meta Ads Manager export.
3. `creative_results` rollup.
4. One diagnostic: "Top creative by ROAS / CPL with sample gate."
5. One recommendation: "Where to put next ₹10k" — sized to spend,
   reusing Constitution card components.

### What to postpone
- Meta / Google connectors (Phase 9.2).
- Experimentation framework (Phase 9.3).
- Industry learning memory (Phase 9.4).
- All autonomy (Phase 9.5).
- Multi-platform parity (TikTok, LinkedIn).
- Anything that requires a new UI primitive.
- Anything that requires a new datastore.

### Why this order
- The 9.1 wedge **proves value in days, not weeks**, with zero
  external dependencies and zero autonomy risk.
- It forces us to nail the **tagging discipline** — the asset that
  every later phase depends on.
- It produces the founder card that answers the highest-value
  question on day one: *"where should my next ₹10k go?"*
- Every later phase becomes additive, not a rewrite.

### Maximum founder value / minimum engineering effort
Single sentence the founder will pay for:

> *"Your family-experience reel is your winner — put your next ₹10k
> behind it targeting parents 35-45. Expected: ~12 more bookings
> this month. Confidence: 80."*

That sentence is Phase 9.1's entire user story. Everything in this
document exists to make that sentence honest, repeatable, and
compounding.

---

## Open questions for sign-off (before any code is written)

1. **CSV-first or connector-first?** This doc recommends CSV-first
   to ship in days. Confirm.
2. **Currency floor:** do we require sales/order data before
   computing ROAS, or do we ship CPL-only first and add ROAS in 9.2?
3. **Industry taxonomy:** what list of industries do we anchor on
   for memory partitioning? (Restaurant / Gym / Real Estate /
   Service Business / Local Business — confirm or extend.)
4. **Autonomy ceiling:** at Phase 9.5, what's the maximum % of daily
   spend the system may shift without explicit founder approval?
5. **k-anonymity floor:** confirm `brand_count ≥ 10` is acceptable,
   or set higher (some industries are thin).
6. **Data retention:** confirm 90 days hot / 24 months rollup or
   adjust.

Awaiting sign-off before touching any file outside this document.
