# DM Tool — Product & Engineering Roadmap

> Executive-level architecture review + ROI-ranked roadmap.
> Date: 2026-06-11. Planning only — no code.
> System of record: **PostgreSQL** (no MongoDB). Incremental delivery,
> reuse-first, tenant-isolation + security preserved.

---

## 0. Executive summary

DM Tool is **further along than a typical pre-revenue SaaS**: the
multi-tenant foundation, AI generation engines, and security/compliance
layers are real and tested (900 backend tests, RLS-ready, hardened). The
gap to "autonomous AI growth platform" is **not the AI — it's the
closed loop**: today the product *generates* and *advises* but does not
*publish*, *measure live*, *bill*, or *act on its own*.

The single highest-leverage theme: **close the loop**. Generation →
schedule/publish → measure (live) → recommend → auto-act. Most of the
pieces exist as islands; the revenue and differentiation come from
connecting them.

**Three things to build next (this quarter):**
1. **Turn on the money** — Stripe billing + usage metering (scaffold exists).
2. **Make the AI proactive** — scheduled AI Coach + weekly content autopilot (engines + Arq exist).
3. **Light the first live integration** — Meta Ads (framework exists), which unlocks live performance intelligence and the autonomous loop.

---

## 1. Current-state inventory (what exists)

### 1.1 Backend modules (29) — `apps/api/aicmo/modules/`
`onboarding · trends · content · ads · visuals · campaigns · bundles ·
landing_pages · leads · analytics · coach · opportunities · context ·
social · learning · performance · integrations · notifications ·
security · team · billing · users · orgs · brands · rbac · audit ·
ai_audit` (+ `observability`).

### 1.2 Frontend routes (~38) — `apps/web/src/app/(app)/`
Home surfaces: `dashboard`, `today`, `today/command-center`, `overview`.
Create: `content`, `ads`, `visuals`, `bundles`, `campaigns`, `campaign-lab`.
Grow: `leads`, `opportunities`, `grow/market-intelligence`, `trends`, `social`.
Measure: `analytics`, `performance`, `landing-pages`, `library`.
Advisor: `ai-coach`.
Settings: `organization`, `team`, `billing`, `settings/*` (org, team, billing, integrations, notifications, security, usage).
Onboarding: `onboarding`, `onboarding/classic`, `onboarding/org`.

### 1.3 Database (43 tables) — PostgreSQL 16, Alembic head `0032`
Identity/tenancy (9), generated assets + intelligence (~18), platform
(security/billing/notifications/integrations/audit/rate-limit, ~16).
Performance indexes (0031) + RLS policies dormant (0032) in place.

### 1.4 AI capabilities (real)
- **LLM router** (`llm/router.py`) — Anthropic (Sonnet 4.6 default) / OpenAI / Google, structured-output validated.
- **Generators**: content, ads, visuals (OpenAI Images), campaigns, bundles — all with strategy envelopes + creative tagging.
- **Intelligence**: Lead Intelligence (heuristic prescorer + LLM ranking), Opportunity Discovery (center report), AI Coach (weekly plan, reality check, analytics summary), Learning Lab (experiment tracking), Performance Intelligence (CSV diagnostics + recommender), Market Intelligence, onboarding Business Analysis.

### 1.5 Infrastructure (real)
- **Arq job queue + worker** (`queue/worker.py`) — background/scheduled work is feasible (not yet heavily used; generation runs inline today).
- **Auth**: Clerk (demo/clerk/hybrid), JWT hardened, prod boot guards.
- **Security**: global rate limit, prompt sanitizer, Sentry scrubber, AI audit trail, RLS readiness.
- **Media**: local disk + HMAC signed URLs (S3 is post-MVP).

---

## 2. Feature status matrix (vision × readiness)

Legend — ✅ done · 🟡 partial · 🟥 not started. Effort in person-weeks (PW).

| Vision feature | Backend | Frontend | Database | Status | Missing pieces | Risk | Biz impact | Effort |
|---|---|---|---|---|---|---|---|---|
| **Lead Intelligence Engine** | ✅ | ✅ | ✅ | **Mature** | enrichment, auto follow-up, intent signals | Low | High | 3 PW |
| **AI Growth Command Center** | ✅ | ✅ | ✅ | **Done (advisory)** | make it *act* (autopilot hooks) | Med | High | 4 PW |
| **Content Studio** | ✅ | ✅ | ✅ | **Mature** | scheduling/publishing | Low | High | — |
| **Ads Studio** | ✅ | ✅ | ✅ | **Mature** | live platform push | Low | High | — |
| **Creative Studio (images)** | ✅ | ✅ | ✅ | **Done** | brand-kit/templates | Low | Med | 2 PW |
| **Reels/Shorts Generator (video)** | 🟥 (scripts only) | 🟡 | 🟡 | **Not started (video)** | video model, render pipeline, storage | High | High | 6–8 PW |
| **Landing Page Intelligence** | 🟡 (build+capture+attribution) | ✅ | ✅ | **Partial** | A/B testing, AI CRO, analytics-driven optimization | Med | High | 4 PW |
| **Campaign Performance Intelligence** | 🟡 (CSV only) | ✅ | ✅ | **Partial** | live ad-platform data, ROAS, revenue attribution | Med | Very High | 4 PW* |
| **AI Recommendations Engine** | ✅ | ✅ | ✅ | **Mature** | act-on-recommendation loop | Low | High | — |
| **Opportunity Discovery Engine** | ✅ | ✅ | ✅ | **Mature** | execution loop (opp → auto-draft) | Low | High | 2 PW |
| **AI Coach** | ✅ | ✅ | ✅ | **Mature** | proactive delivery (scheduled) | Low | High | 2 PW |
| **Multi-tenant SaaS** | ✅ | ✅ | ✅ | **Mature** | usage limits, agency tier | Low | High | — |
| **Enterprise security** | ✅ | ✅ | ✅ | **Strong** | RLS activation, SSO, SOC2 exports | Low | Med | 6 PW |
| **PostgreSQL system of record** | ✅ | — | ✅ | **Done** | backups/DR infra (ops) | Low | — | — |
| **pgvector memory/search** | 🟥 (readiness only) | 🟥 | 🟡 | **Not started** | extension, embeddings, ANN, RAG wiring | Med | Med-High | 4 PW |
| **Billing / monetization** | 🟡 (scaffold, no Stripe) | 🟡 | ✅ | **Partial** | Stripe Checkout + webhooks + metering | Low | **Critical** | 3 PW |
| **Notifications delivery** | 🟡 (prefs only) | 🟡 | ✅ | **Partial** | email/Slack dispatcher | Low | Med-High | 2 PW |
| **Integrations (connectors)** | 🟡 (framework, all stubs) | 🟡 | ✅ | **Partial** | first real OAuth connector (Meta) | High | Very High | 5 PW |
| **Content scheduling/publishing** | 🟥 | 🟥 | 🟡 | **Not started** | scheduler, social write APIs, calendar | Med | Very High | 5 PW |

\* Campaign Performance Intelligence live effort assumes the Integrations
connector (its hard dependency) is delivered separately.

---

## 3. Unfinished / partial / duplicated / abandoned

### 3.1 Partial (scaffolded, not revenue-complete)
- **Billing** — plans/subscriptions/invoices tables + "honest placeholder" upgrade flow; **no Stripe**, no metering enforcement.
- **Integrations** — OAuth framework + token encryption + 6 provider **stubs** (`NotImplementedError`); **zero live connectors**.
- **Notifications** — preference matrix complete; channels report `delivery_status='placeholder'`; **no dispatcher**.
- **Social** — read-only intelligence + Instagram **stub**; manual-import path only.
- **Performance Intelligence** — strong, but **CSV-import only** (no live pull).
- **Landing Pages** — build + capture + attribution; **no CRO/A-B "intelligence."**

### 3.2 Duplicated / overlapping surfaces (UX debt, low urgency)
- **Four "home" surfaces**: `dashboard`, `today`, `today/command-center`, `overview` — overlapping intent; the 10.3 "Founder Simplification" migration is **partially complete** (tasks #265 command palette, #268 create/results consolidation, #269 test sweep still open).
- **Three onboarding routes**: `onboarding`, `onboarding/classic`, `onboarding/org`.
- **Two coach surfaces**: `ai-coach` page + coach cards embedded across dashboards.
- `next.config.ts` still carries **legacy→new rewrites** (`/grow/leads`→`/leads`, etc.) that Slice 6 was meant to finalize.

### 3.3 Abandoned/superseded (already cleaned or safe to retire)
- `lib/advanced-mode.*` (removed earlier — consolidated into `useViewMode`).
- Legacy onboarding (`/onboarding/classic`) — keep only as fallback; schedule removal once `/onboarding/org` is the sole path.

**Recommendation:** treat 3.2 as a single ~2 PW "UX consolidation" cleanup, scheduled *after* revenue features (it's low ROI but reduces support load and onboarding confusion).

---

## 4. Gap analysis — current product vs autonomous growth platform

| Capability axis | Today | Autonomous-platform target | Gap |
|---|---|---|---|
| **Generate** | ✅ strong (text, image, campaigns) | + video (reels/shorts), brand-kit consistency | video pipeline |
| **Distribute** | 🟥 manual copy/paste | scheduled multi-channel auto-publish | scheduler + write integrations |
| **Measure** | 🟡 first-party (leads/pages) + CSV | live cross-platform ROAS/revenue | live integrations |
| **Recommend** | ✅ strong (coach, opportunities) | proactive + delivered | notification dispatcher + cron |
| **Act** | 🟥 human-in-loop only | autonomous opp→draft→publish→optimize | closed-loop engine |
| **Remember** | 🟡 SQL only | semantic brand memory, RAG | pgvector |
| **Monetize** | 🟡 scaffold | metered subscriptions | Stripe + limits |
| **Enterprise** | ✅ strong base | RLS-on, SSO, SOC2, white-label | activation + auth federation |

**The core insight:** DM Tool has world-class *Generate* and *Recommend*,
but is missing *Distribute*, live *Measure*, and *Act* — exactly the
three that turn an "AI content tool" into an "autonomous growth
platform," and exactly where competitors are weak.

---

## 5. Phased roadmap

### PHASE A — Revenue Features (Quarter 1)
*Goal: monetize + make the existing AI reach the customer proactively.*

- **Deliverables:** Stripe billing (Checkout + webhooks + plan sync); usage metering + plan-limit enforcement; notification email dispatcher; proactive AI Coach (scheduled weekly brief); AI content **Autopilot** (auto-generated weekly pack from existing generators); Landing Page A/B + AI CRO.
- **Architecture:** reuse `billing` + `usage_event` tables; add a thin `payments` adapter (Stripe SDK) behind the existing service; deliver via Arq scheduled jobs; notifications dispatcher as a new `notifications/dispatch/` package with pluggable channels (email first via Resend/SES).
- **Database impact:** additive — `subscription` gains Stripe IDs; new `notification_delivery` log; `landing_page_variant` + `landing_page_event` tables for A/B. No breaking changes.
- **APIs affected:** `billing/*` (new checkout/webhook endpoints), `notifications/*` (delivery status becomes real), `landing-pages/*` (variants), new `coach/schedule`.
- **UI affected:** `settings/billing` (real upgrade), `settings/notifications` (live channels), `landing-pages` (variant editor + results), dashboards (autopilot toggle).
- **Testing:** Stripe webhook signature tests (mirror the Clerk-webhook pattern); metering-limit invariants; email-dispatch idempotency; A/B assignment determinism + tenant isolation on new tables.
- **Security:** Stripe webhook HMAC verification; `STRIPE_SECRET_KEY` in the secret runbook + prod boot guard; email templates run through the prompt/PII scrubber; new tables inherit `TenantMixin` + RLS policy.
- **Success metrics:** first paid conversion; MRR; % founders receiving weekly brief; autopilot adoption; landing-page CVR lift.

### PHASE B — AI Automation (Quarter 2)
*Goal: deepen the AI so it produces more, remembers, and self-improves.*

- **Deliverables:** Reels/Shorts **video** generator; pgvector **brand memory** + semantic asset search; Lead follow-up automation (AI reply drafts + sequences); Opportunity→draft execution loop; Creative brand-kit/templates.
- **Architecture:** add a `video` provider behind the existing visuals provider abstraction (same pattern as OpenAI Images); embeddings written on asset create via an Arq job → `*_embeddings` tables (pgvector); RAG context feeds the existing `context.builder` and Coach prompts.
- **Database impact:** `CREATE EXTENSION vector` (switch dev image to `pgvector/pgvector:pg16`); new tenant-scoped `content_embeddings` + `rendered_video` tables with HNSW + brand_id pre-filter (per `POSTGRES_ARCHITECTURE.md` §4).
- **APIs affected:** new `visuals/video/*`, `library/search` (semantic), `leads/{id}/draft-reply`, extends `context` with retrieved memory.
- **UI affected:** Creative Studio gains a video tab; `library` gains semantic search; lead drawer gains AI reply.
- **Testing:** video render cap + cost governance (reuse the 20/day pattern); embedding-write idempotency; **semantic search must pre-filter by brand_id** (tenant-isolation test); RAG never crosses tenants.
- **Security:** video storage signed-URL only; embeddings carry `organization_id NOT NULL` (RLS-ready); model-cost caps; generated video excluded from AI-audit content (as today).
- **Success metrics:** video generation adoption; assets-reused-via-search rate; lead reply time ↓; opportunity→published conversion.

### PHASE C — Autonomous Growth Engine (Quarter 3)
*Goal: close the loop — measure live and act without a human.*

- **Deliverables:** first **live ad integration** (Meta, then Google); **live** Campaign Performance Intelligence (ROAS/CPL/revenue); content scheduling + **auto-publish** to social; **closed-loop optimization** (auto-adjust/regenerate based on live performance); cross-channel orchestration.
- **Architecture:** implement the `MetaProvider` against the existing `IntegrationProvider` abstraction (OAuth + token refresh + sync); Arq sync jobs pull metrics into `performance_events`; the Learning Lab + recommender consume live data; an `autopilot` orchestrator turns top opportunities into scheduled, attributed posts and watches outcomes.
- **Database impact:** reuse `performance_events`/`performance_signals` (add `source='meta'`); new `scheduled_post` + `publish_result` tables; `integration_credential` already encrypted (Fernet) — wire the **two-key rotation** (Tier-3 from the security review).
- **APIs affected:** `integrations/meta/*` (connect/sync), `performance/*` (live source), new `schedule/*`, `autopilot/*`.
- **UI affected:** Integrations (real connect flow), Performance (live ROAS), a Calendar/Scheduler surface, Command Center (autopilot status + approvals).
- **Testing:** OAuth state-token security; provider rate-limit/backoff; **every Arq job must carry tenant context** (the A5 limitation — extend `bind_tenant_context` to workers); auto-publish requires explicit per-action authorization (no surprise posting); live-metric tenant isolation.
- **Security:** outbound write-scope tokens are high-value — scope minimally, encrypt, rotate; autonomous actions are **audited** (AI audit trail already exists) and reversible; human approval gate before first autonomous publish per brand.
- **Success metrics:** connected-account rate; ROAS visibility; auto-published posts; measurable lift from closed-loop optimization; time-saved per founder.

### PHASE D — Enterprise Scale (Quarter 4)
*Goal: unlock larger contracts + agencies; harden for scale.*

- **Deliverables:** **RLS production activation** (readiness done); SSO/SAML; SOC2 audit/compliance exports; agency/multi-brand tier + white-label; customer API + webhooks; PgBouncer + read-replica + backup/DR (ops).
- **Architecture:** activate RLS via the staged plan (`RLS_ACTIVATION.md`); federate Clerk SSO/SAML; expose a scoped public API behind API keys + the existing rate limiter; agency tier reuses `orgs`/`brands` (parent-org → many brands).
- **Database impact:** enable RLS on the 6 tables (non-superuser app role first); add `api_key` + `webhook_endpoint` tables; backups/replica are infra, not schema.
- **APIs affected:** new `/public/v1/*` (keyed), webhook delivery, SSO callback.
- **UI affected:** white-label theming, agency workspace switcher (extends existing org/brand switcher), API-key management in settings.
- **Testing:** RLS acceptance suite (exists) run against live enforcement; SSO flows; API-key scoping + rate-limit; webhook signature + retry; load test behind PgBouncer.
- **Security:** RLS as DB-layer tenant boundary; SSO removes password surface; API keys scoped + revocable + audited; SOC2 control mapping (in `RLS_ACTIVATION.md` §8).
- **Success metrics:** enterprise/agency deals closed; SOC2 readiness; p95 latency under load; zero cross-tenant findings.

---

## 6. Top 20 roadmap by ROI

**Methodology.** `ROI = (Customer Impact × Revenue Impact × Strategic
Importance) ÷ Engineering Effort`, each factor scored 1–5. Effort is
*total* PW including hard dependencies. Higher = build sooner. Reuse of
existing scaffolding lowers effort (raises ROI) — which is why several
"finish what's scaffolded" items top the list.

| # | Item | Phase | CI | RI | SI | Eff | **ROI** | Reuses | Depends on |
|---|---|---|----|----|----|-----|--------|--------|-----------|
| 1 | **Stripe billing activation** | A | 3 | 5 | 4 | 2 | **30.0** | billing scaffold, usage_event | — |
| 2 | **AI content Autopilot** (weekly auto-pack) | A | 5 | 4 | 5 | 4 | **25.0** | generators, bundles, Arq | — |
| 3 | **Live Meta Ads integration** | C | 5 | 5 | 5 | 5 | **25.0** | integ framework, crypto | — |
| 4 | **Content scheduling + auto-publish** | C | 5 | 4 | 5 | 4 | **25.0** | content studio, Arq | #3 (write scope) |
| 5 | **Live Campaign Performance Intelligence (ROAS)** | C | 5 | 5 | 4 | 4 | **25.0** | performance module, learning | #3 |
| 6 | **Closed-loop autonomous optimization** | C | 5 | 5 | 5 | 5 | **25.0** | recommender, opportunities | #3,#5 |
| 7 | **Proactive AI Coach** (scheduled email brief) | A | 4 | 3 | 4 | 2 | **24.0** | coach, Arq | #11 |
| 8 | **Landing Page A/B + AI CRO** | A | 4 | 4 | 4 | 3 | **21.3** | landing_pages, analytics | — |
| 9 | **Usage metering + plan-limit enforcement** | A | 2 | 5 | 4 | 2 | **20.0** | usage_event | #1 |
| 10 | **Reels/Shorts video generator** | B | 5 | 4 | 5 | 5 | **20.0** | visuals provider abstraction | video model |
| 11 | **Notification email dispatcher** | A | 4 | 3 | 3 | 2 | **18.0** | notification prefs | email SDK |
| 12 | **Lead follow-up automation** | B | 4 | 4 | 3 | 3 | **16.0** | leads/intelligence | #11 |
| 13 | **Cross-channel orchestration** | C | 4 | 4 | 5 | 5 | **16.0** | campaigns, scheduler | #3,#4 |
| 14 | **pgvector brand memory + semantic search** | B | 3 | 3 | 5 | 3 | **15.0** | RLS readiness, context builder | pgvector image |
| 15 | **Agency / multi-brand tier** | D | 2 | 4 | 3 | 2 | **12.0** | orgs/brands | #1,#9 |
| 16 | **Asset library semantic search (UI)** | B | 3 | 2 | 3 | 2 | **9.0** | library page | #14 |
| 17 | **Customer API + webhooks** | D | 2 | 3 | 3 | 3 | **6.0** | rate limiter, auth | — |
| 18 | **SOC2 audit/compliance exports** | D | 1 | 3 | 4 | 3 | **4.0** | audit/ai_audit tables | — |
| 19 | **RLS production activation** | D | 1 | 2 | 4 | 2 | **4.0** | RLS readiness (done) | non-superuser role |
| 20 | **SSO / SAML** | D | 1 | 4 | 3 | 4 | **3.0** | Clerk | — |

*Just below the cut (defer):* UX consolidation / onboarding cleanup
(ROI ~3, debt), white-label (ROI ~1.5), PgBouncer/scale infra (ops-timed).

---

## 7. Dependency-aware execution sequence

ROI ranks *value*; dependencies dictate *order*. Recommended sequence
(the email dispatcher, for instance, must precede the proactive Coach
even though the Coach scores higher):

**Q1 (revenue):** 1 Stripe → 9 Usage limits → 11 Email dispatcher → 7 Proactive Coach → 2 Autopilot → 8 Landing A/B.
**Q2 (automation):** 14 pgvector memory → 10 Reels/Shorts → 12 Lead follow-up → 16 Asset search.
**Q3 (autonomy):** 3 Meta integration → 5 Live performance → 4 Scheduling/publish → 13 Orchestration → 6 Closed-loop.
**Q4 (enterprise):** 19 RLS activation → 18 SOC2 exports → 15 Agency tier → 17 Customer API → 20 SSO → (white-label, scale infra).

---

## 8. The five executive questions

1. **What should we build next?**
   **Stripe billing + usage metering** (turn on revenue — the scaffold is
   already there), immediately followed by **AI Autopilot + proactive
   Coach** (make the AI you've already built reach the customer without
   them asking). Highest ROI, mostly reuse, low risk.

2. **What generates revenue fastest?**
   **Stripe activation (#1)** — it's the literal payment pipe and the
   scaffolding exists, so it's ~2 PW to first dollar. **Usage metering
   (#9)** right after makes tiered pricing enforceable. Together they
   convert the existing product into a paying SaaS without new features.

3. **What creates the biggest competitive advantage?**
   The **autonomous loop** — Meta integration (#3) → live ROAS (#5) →
   auto-publish (#4) → closed-loop optimization (#6). Competitors stop at
   "AI writes your post." DM Tool would *publish it, measure it live, and
   improve it automatically*. That, plus **pgvector brand memory (#14)**
   so the AI compounds knowledge of each brand over time, is the moat.

4. **What should wait until later?**
   Enterprise federation (SSO/SAML #20, white-label), customer API (#17),
   and the UX/onboarding consolidation. All are real but low ROI now —
   they unlock larger deals you can't close until the core loop and
   billing exist. RLS *activation* also waits (readiness is done; flip it
   when the first enterprise prospect requires DB-layer isolation).

5. **What can be reused from the current implementation?**
   Almost everything. **Billing tables, usage_event, the Integrations
   OAuth+encryption framework, the visuals provider abstraction (→ video),
   the generators (→ autopilot), the Coach + Opportunities engines (→
   proactive/autonomous), Arq (→ scheduling), RLS readiness (→ enterprise),
   and the performance module (→ live ROAS)** are all directly reusable.
   The roadmap is deliberately "finish and connect the islands," not
   "rewrite." Net-new builds are only: video generation, pgvector
   embeddings, and the Stripe/email/SSO adapters.

---

## 9. Constraint adherence

- **PostgreSQL only** — every new table is Postgres; pgvector is a PG extension. No MongoDB.
- **Reuse-first** — §8.5; net-new is minimized to 3 adapters + 2 capabilities.
- **Tenant isolation** — every new table inherits `TenantMixin` + a RLS policy; semantic search pre-filters by `brand_id`; Arq jobs must carry tenant context (explicit Phase-C requirement).
- **Security preserved** — new webhooks reuse the HMAC-verify pattern; new secrets join the runbook + boot guard; autonomous actions are audited + reversible + approval-gated.
- **Backward compatible** — all DB changes additive; billing/notifications/integrations move from "placeholder" to "real" without breaking current contracts.
- **Incremental** — four quarterly phases, each shippable independently, each with tests + a working preceding state.

---

## 10. Top risks to flag now

| Risk | Phase | Mitigation |
|---|---|---|
| Autonomous publishing posts something wrong to a real account | C | Human approval gate per brand before first auto-publish; full audit + undo |
| Live integration token (write scope) leak | C | Minimal scope, Fernet at rest, two-key rotation, RLS on credentials |
| Arq jobs run without tenant scope → cross-tenant data in background work | B/C | Extend `bind_tenant_context` to workers BEFORE any tenant-scoped job ships |
| Video + embeddings model cost blowout | B | Reuse the per-user daily-cap governance pattern |
| Stripe webhook spoofing | A | HMAC signature verification (mirror Clerk webhook) |
| Enabling RLS with a superuser app role (silent no-op) | D | Pre-flight gate already documented in `RLS_ACTIVATION.md` |
