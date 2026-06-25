# DM Tool — Outcome-Driven Alignment Review

> Positioning correction: DM Tool is an **AI Growth Platform**, not an AI
> design generator. The user thinks in business outcomes ("I need more
> restaurant customers"), never in asset types ("make me a poster").
> This review audits every current + planned system against that model and
> specifies the corrections. Architecture only — no code.
> Date: 2026-06-11.

---

## 0. Verdict

**The foundation already agrees with this positioning — the misalignment
is at the entry point.** The CLAUDE.md constitution has mandated
outcome-first since day one ("DM Tool is an AI Digital Marketing
Consultant… business impact first… ship questions, not numbers"). The
campaign link, the Opportunity Engine, the Coach, and the autonomous-loop
roadmap are all outcome-shaped. What's wrong is *who drives*: today the
**asset surfaces are the front door** (studios where users pick
content/ad/visual types; a Creative Studio plan organized around
composers per creative type). In the corrected model, **the Campaign
Objective is the front door and assets are the back office** — produced
by strategy, not requested by users.

One genuinely new first-class object (`growth_objective`) + one
orchestration service (the Strategy Engine) closes the structural gap.
Everything else is **repositioning, not rebuilding** — and notably, no
shipped table needs renaming (the creative core's media-agnostic design
survives this pivot untouched, which is the point of having built it that
way).

**Verified: zero industry hardcoding exists.** `business_profiles.industry`
is free text (validators only reject gibberish/generic); the industry
strings found in code are prompt *examples*, not enums. The "any industry,
no hardcoding" requirement is already structurally true and must stay a
review rule: **industry is always free-text context flowing into prompts,
never a code branch.**

---

## 1. The primary object chain → concrete systems

The requested chain maps onto the platform like this — four of six links
already exist:

| Chain link | System | Status |
|---|---|---|
| **Campaign Objective** | **`growth_objective` (NEW)** — the outcome ask, KPI, target, timeframe | ❌ missing as a first-class object (today: a free-text `campaign_plans.goal` string) |
| **Campaign Strategy** | `campaign_plans` (strategy JSONB, calendar, platforms) + the **Strategy Engine (NEW service)** that *derives* it from the objective | 🟡 artifact exists; the objective→strategy derivation is manual |
| **Creative Assets** | Creative Core (`creative_project.campaign_id` FK already exists) + composers | ✅ shipped (V0) / designed (Studio) |
| **Distribution** | scheduling + publish via integrations | 🟡 designed (roadmap Phase C) |
| **Measurement** | analytics (first-party leads) + live ROAS (Phase C); KPI resolved **per objective kind** | 🟡 partial |
| **Optimization** | Learning Lab + recommender + closed loop (Phase C) | 🟡 partial |

### 1.1 `growth_objective` (the one new table — additive)
```
id, organization_id, brand_id, user_id          (TenantMixin — RLS-registered)
statement          text         -- the founder's own words: "I need more software engineers"
objective_kind     FK → objective_kind catalog  -- the OUTCOME taxonomy (§2)
target_value       numeric?     -- e.g. 50 (applications), nullable = "more"
target_timeframe   daterange?   
audience_hypothesis JSONB       -- AI-derived, editable
status             draft|active|achieved|paused|archived
kpi_snapshot       JSONB        -- measured progress (refreshed by jobs)
```
`campaign_plans` gains a nullable `objective_id` (additive). The chain in
FKs: `growth_objective ← campaign_plans ← creative_project ←
creative_asset/variant ← published_ref → performance`. **Every asset is
traceable to the business outcome it serves** — which is what makes
outcome-level measurement and optimization possible.

### 1.2 The objective taxonomy — outcomes, not industries (DB catalog)
A new `objective_kind` catalog (same DB-configurable pattern as `plan` /
`creative_format` — tunable without deploy):

| kind | example founder statements | KPI source |
|---|---|---|
| `leads` | "more real estate leads", "more cybersecurity clients" | leads table (exists) |
| `sales` / `revenue` | "more SaaS signups", "more orders" | conversions/ROAS (Phase C) |
| `bookings` | "more restaurant customers", "more clinic appointments" | bookings = lead subtype w/ intent |
| `applications` | "more software engineers" | applications = lead subtype |
| `registrations` | "more webinar registrations" | registrations = lead subtype |
| `awareness` | "get known in my city" | reach/engagement (Phase C) |
| `retention` | "more repeat customers" | repeat-engagement (later) |

Crucial design point: **outcomes are industry-agnostic** — a "booking"
works identically for a restaurant, a clinic, and a salon. Industry never
appears in this taxonomy; it lives only in `business_profiles.industry`
(free text) and flows into prompts as *context*. This is how "support any
industry, no hardcoding" is enforced structurally: there is no industry
column anywhere in the objective/strategy/creative chain.

Note: `CampaignType` today conflates outcomes (`lead_generation`,
`brand_awareness`) with tactics (`seasonal`, `retargeting`,
`product_launch`). The correction separates them: `objective_kind` = the
outcome; campaign tactics stay on `campaign_plans` as strategy choices the
engine makes. No migration of `CampaignType` needed (backward compat) —
the Strategy Engine maps objective → tactic(s).

---

## 2. The Strategy Engine (the new orchestration service)

The 13-step flow the positioning demands, mapped to what runs it:

```
"I need more software engineers."           (objective intake — NL, sanitized)
   1  understand objective    → LLM → growth_objective (kind=applications, audience hypothesis)
   2  identify audience       → business_profile + market intelligence (exists) → audience JSONB
   3  build strategy          → Strategy Engine LLM → campaign_plans (channels, tactics, calendar, budget split)
   4  select channels         → strategy output, constrained by connected integrations + format catalog
   5  creative assets         → asset plan → N creative_projects → composers (poster/video/… = HIDDEN implementation detail)
   6  copy                    → content engine (exists) → text layers / captions
   7  landing page assets     → landing_pages module (exists) — attached for attribution (already wired)
   8  videos if needed        → video subsystem (shipped V0) — strategy decides, not the user
   9  ad variations           → ads engine (exists) → ad creatives
  10  A/B variants            → creative_variant + design forks (Studio §)
  11  publish                 → distribution (Phase C; approval-gated)
  12  measure                 → KPI per objective_kind (leads now; ROAS Phase C)
  13  optimize                → Learning Lab + closed loop (Phase C) — winners reshape the next asset plan
```

Implementation shape: `modules/growth/` (or extend `campaigns/`) — an
LLM-driven planner with a **structured StrategyPlan schema** (Pydantic,
constitution rule) whose output is an *asset plan*: a list of
`(creative_type, format_slug, brief, variant_spec)` entries the engine
turns into `creative_project` rows and enqueues through the existing
tenant-job pipeline. **Every existing engine (content, ads, visuals,
video, landing pages, bundles) becomes a callee of the Strategy Engine.**
The `bundles` orchestrator is the embryonic version of this — it already
fans one objective into multiple assets; the Strategy Engine generalizes
it with the objective object, channel selection, and the measurement loop.

The Constitution's AI-recommendation contract applies to the strategy
itself: every plan ships with recommendation + reason + confidence +
expected result ("Expected: 8–15 engineering applications in 3 weeks").

---

## 3. System-by-system alignment audit

| System | Current/planned state | Outcome-driven correction |
|---|---|---|
| **Creative Studio (entry)** | Studio doc organizes around per-type composers; users create `creative_project`s directly with a creative_type | Composers stay (implementation detail) but become **machine-invoked by the asset plan**. Direct project creation survives only as a Pro-mode escape hatch. **Simple Mode never shows asset-type pickers** — it shows objectives, campaigns, results. (Maps exactly onto the existing Simple/Professional toggle.) |
| **Templates** | Studio doc: "curated built-ins per creative type" — a template-*category* model | **Corrected to generative**: layouts/color systems/visual styles are **dynamically composed** from a library of *layout primitives + design principles* (grids, hierarchy, contrast, safe zones), parameterized by industry/audience/objective/platform/brand kit. `creative_template` (no schema change) stores *generated* and *user-saved* starting points — a cache of good outputs, never a browsable category catalog of "restaurant templates." No industry-tagged template taxonomy, ever. |
| **Asset Library** | Cross-media grid by media/creative type | Add the **outcome lens**: filter/group by objective + campaign ("everything generated for the engineer-hiring push") via the FK chain. Type filters stay for Pro mode. |
| **AI Editing** | NL → EditOps (aligned already — users speak intent, not tools) | Keep. Add objective-aware edit context ("punchier for job-seekers") — the design's linked objective/audience flows into the edit prompt. No structural change. |
| **Veo / video** | A media type inside the studio (already corrected from standalone) | Strategy Engine decides *when video is the right tactic* (step 8). Users never ask for "a reel" in Simple Mode; they get one when the strategy calls for it. |
| **Publishing** | Phase C scheduling/auto-publish | Publishes **campaigns** (asset plans with timing), not individual files. Approval gates per brand unchanged. |
| **Analytics** | Constitution-compliant BusinessMetric surfaces; lead attribution chain exists | Measurement becomes **objective-first**: the headline metric per objective is its `objective_kind` KPI vs `target_value` ("32 of 50 applications — on track"). Asset/channel metrics live a level down (Pro mode / technical details). |
| **Optimization** | Learning Lab tracks per-asset experiments | Optimizes **toward the objective KPI**, not engagement proxies: variant winners are judged by contribution to the outcome (leads/applications), feeding the next asset plan. The experiment chain gains `objective_id` context via the existing FKs — no schema change. |
| **Onboarding / Coach / Opportunities** | Already outcome-first (audit confirms) | Opportunities + Coach actions become *objective proposals* — "accept" creates a `growth_objective` and triggers the Strategy Engine. This closes the recommendation→execution loop at the right altitude. |

New creative types required (brochure, flyer, landing-page assets, email
creatives, ad creatives): **string enum values + composers — zero schema
changes**, by the core's design.

---

## 4. What changes in the build sequence

The approved execution order (0→6) stands; this re-frames *what CS-phases
serve* and inserts the objective layer early so nothing is built
asset-first and re-platformed later:

| Adjusted | Scope |
|---|---|
| **CS1 (amended)** | Design model **+ `growth_objective` + `objective_kind` catalog + `campaign_plans.objective_id`** (one combined additive migration) |
| **CS2** | Render + export (unchanged) |
| **CS3 (amended)** | **Strategy Engine v1** (objective → strategy → asset plan → projects) + the first composers as its callees — NOT user-facing type pickers |
| **CS4** | AI editing (unchanged) |
| **CS5 (amended)** | Frontend: the **objective-first intake** ("What do you want more of?" — reusing the conversational-onboarding pattern) + campaign command center; the canvas editor is Pro-mode |
| **CS6** | Polish (unchanged) |

Phases 2–6 of the main roadmap (Autopilot, Proactive Coach, Publishing,
Meta, ROAS, closed loop) are **unaffected in content and strengthened in
framing** — the Autopilot becomes "the Strategy Engine on a schedule," and
the closed loop optimizes objective KPIs.

---

## 5. Constitution addendum (proposed)

One paragraph to add to CLAUDE.md so the rule outlives this review:

> **OUTCOME-DRIVEN RULE.** The primary object of DM Tool is the Campaign
> Objective (a business outcome: leads, sales, bookings, applications,
> registrations, revenue, awareness, retention). Asset types (poster,
> banner, reel, video, ad, email, brochure…) are implementation details
> that Simple Mode never surfaces as choices. Industry is always free-text
> context — never an enum, never a code branch, never a template category.
> Every creative artifact must be traceable (by FK) to the objective it
> serves, and every optimization decision is judged against that
> objective's KPI.

---

## 6. Explicitly unchanged (no rework)

All shipped infrastructure survives intact: Creative Core schema (no
renames — the media-agnostic bet pays off again), provider abstractions
(Video/TTS/Image/Storage), Phase 0 job harness, Phase 1 metering/billing,
RLS readiness, security controls, the layer-based Studio design (it is the
*execution engine*; only its entry point moves), and the
`visuals`/`content` modules (untouched; they become Strategy Engine
callees).

## 7. Open decisions (before the amended CS1)
1. **Where the Strategy Engine lives** — new `modules/growth/` (recommended: it orchestrates across campaigns/creative/landing/content) vs extending `modules/campaigns/`.
2. **Objective intake UX** — conversational (reuse the 2.0 onboarding stepper pattern; recommended) vs single form.
3. **`objective_kind` seed list** — the 7 kinds above as the catalog seed (DB-tunable later)?
4. **Bookings/applications/registrations as lead subtypes** — measured via a `lead.intent_kind` tag (additive column) vs separate tables (recommend: tag — one funnel, many labels).
