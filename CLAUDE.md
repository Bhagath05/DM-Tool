# AI-CMO — conventions

Read this before touching code in this repo.

---

# 🚨 FINAL PRODUCT CONSTITUTION — DM TOOL

**READ FIRST. OVERRIDES ALL UI, UX, DASHBOARD, REPORTING, ANALYTICS, AI OUTPUT, AND FEATURE DECISIONS.**

This constitution takes precedence over every other section in this document and over any prior design pattern. If anything below this constitution conflicts with it, the constitution wins.

---

## WHAT DM TOOL IS

DM Tool is **NOT** an analytics dashboard.

DM Tool is **an AI Digital Marketing Consultant**.

The product exists to help business owners:

- Get more leads
- Get more customers
- Increase revenue
- Save time
- Make better marketing decisions

Users should feel like they hired a senior marketing consultant, not opened another reporting tool.

DM Tool should feel like:

- ✅ A Digital Marketing Advisor
- ✅ A Growth Consultant
- ✅ A Business Coach
- ✅ A Strategic Marketing Partner

DM Tool should NOT feel like:

- ❌ Google Analytics
- ❌ Looker Studio
- ❌ Meta Ads Manager
- ❌ A reporting dashboard
- ❌ A KPI spreadsheet

---

## WHO WE BUILD FOR

Primary users:

- Small business owners
- Startup founders
- Local businesses
- Service providers
- First-time entrepreneurs
- Non-technical users

Assume most users do NOT understand: CTR, CPC, CPM, ROAS, bounce rate, conversion rate, attribution, retargeting, SEO terminology.

**If a first-time business owner cannot understand a page within 10 seconds, the design fails.**

---

## THE 10-SECOND RULE

Every page must answer within 10 seconds:

1. What is happening?
2. Is it good or bad?
3. What should I do next?

If those answers are not immediately obvious, redesign the page.

---

## THE GOLDEN RULE

Never show a metric without explaining:

1. What it means
2. Why it matters
3. Whether it is good or bad
4. What action should be taken

❌ Bad:
```
CTR: 3.2%
```

✅ Good:
```
CTR: 3.2%
What it means:      3 out of every 100 people who see your ad click on it.
Status:             Above average.
Recommended Action: Increase budget by 10%.
```

---

## BUSINESS IMPACT FIRST

Every metric must connect to a business outcome. Metrics alone are never enough.

Every insight must map to one of these five **impact categories**:

- **Revenue Impact**
- **Lead Impact**
- **Customer Impact**
- **Time Impact**
- **Cost Impact**

Every insight must answer:

> **"So what does this mean for my business?"**

If that question is not answered, the insight is incomplete.

---

## EVERY INSIGHT MUST END WITH ACTION

Never stop at reporting.

❌ Bad:
```
Traffic dropped 20%.
```

✅ Good:
```
Traffic dropped 20%.
Likely Cause:       Posting frequency decreased.
Recommended Action: Publish 3 posts this week.
Expected Result:    Traffic may recover within 7–14 days.
```

---

## AI RECOMMENDATION CONTRACT

Every AI recommendation MUST include all four of:

1. **Recommendation**
2. **Reason**
3. **Confidence Score** (0–100)
4. **Expected Result**

Example:
```
Recommendation:  Increase Facebook budget by ₹2,000.
Reason:          Facebook generated 35% cheaper leads than Instagram.
Confidence:      87%
Expected Result: 15–25 additional leads.
```

**No recommendation may be shown without all four fields.** Backend Pydantic schemas must refuse to ship without them. Frontend components must refuse to render without them.

---

## THREE-QUESTION SCREEN TEST

Every screen must answer:

1. What is happening?
2. What should I do?
3. What result can I expect?

Applies to: Dashboard, Leads, Analytics, Campaigns, SEO, Reports, Trends, AI Coach, Generators, and every future feature.

If a screen cannot answer all three, it is incomplete.

---

## DASHBOARD PRIORITY ORDER

Always show information in this order:

1. **AI Coach**
2. **Opportunities**
3. **Recommended Actions**
4. **Leads**
5. **Revenue Impact**
6. **Campaign Results**
7. **Analytics**

**Analytics should never be the first thing users see.**

---

## AI COACH RULE

The AI Coach is the centre of the product.

Every dashboard visit should answer:

- What happened?
- Why did it happen?
- What should I do next?
- What result can I expect?

The AI Coach should feel like a real consultant sitting beside the user.

---

## DUAL-LAYER INFORMATION SYSTEM

Every metric has two layers.

**Layer 1 (Default) — simple business language.**
**Layer 2 (Optional) — technical marketing details.**

Example:
```
Lead Cost: ₹120 per lead

Simple Explanation: You spend ₹120 to get one potential customer.
Status:             Good
Recommended Action: Keep this campaign running.

[Show Technical Details]
  CPL ₹120
  CTR 3.4%
  CPC ₹11
```

---

## SIMPLE MODE VS PROFESSIONAL MODE

| Mode | Default? | What it shows |
|---|---|---|
| **Simple Mode** | ✅ Yes | Business language, recommendations, AI explanations, minimal jargon |
| **Professional Mode** | Opt-in | Advanced metrics, full charts, marketing terminology, detailed breakdowns |

**Simple Mode is always the default.**

---

## SHIP QUESTIONS, NOT NUMBERS

Never surface metrics without context. Users should leave a page thinking:

> "I know what to do next."

Not:

> "I saw some numbers."

If you cannot write a business-impact line for a metric, surface it as a question to investigate, not as a fact.

---

## CREATIVE STUDIO CONSTITUTION (platform laws)

Three laws govern everything the Creative Studio builds. They are
**platform laws, not implementation details** — a change that violates one
is a bug against the platform, not a tradeoff. Canonical specs:
`docs/product/OUTCOME_TO_CREATIVE_SYSTEM.md`,
`docs/product/CREATIVE_STUDIO_ARCHITECTURE.md`,
`docs/product/HUMAN_AI_COLLABORATION_INVARIANT.md`.

### LAW 1 — Outcome-Driven Platform
DM Tool's primary object is the **business outcome** (the Growth
Objective), never an asset type. The user asks for outcomes ("get leads",
"get bookings", "hire", "drive installs"); the **Strategy Engine** decides
the creative strategy; the **Creative Studio** produces and edits the
assets. Asset types (poster/carousel/reel/ad) are implementation details
Simple Mode never surfaces. Every artifact is traceable by FK to the
objective it serves and judged on that objective's KPI.

### LAW 2 — No Template Categories
There are **no predefined template categories and no industry-specific code
branches.** No "restaurant/healthcare/hiring templates", no industry enum,
no `if industry == …` anywhere in composition, no industry column on
templates/formats/objectives. Industry is **free-text prompt context
only.** Templates are **generated** from design primitives + layout
systems + brand tokens + objective composition rules, parameterized by
(objective, audience, brand, platform, strategy). `creative_template` rows
are generated/user-saved outputs (a cache of good designs), never a curated
catalog. Acceptance test: swapping the industry string changes copy/imagery
but exercises the *same* composers, primitives, formats, and code paths.

### LAW 3 — Human + AI Collaboration (one design, one write path)
Creative Studio has three modes — **AI** (AI creates), **Guided** (AI
modifies), **Pro** (human modifies) — that all operate on the **same
`creative_design`** through **one** revision pipeline. There are **no
mode-specific code paths or tables**; `mode` is request metadata, never a
fork in the data model. **No code may mutate a design in place:** every
change (AI or human) goes through **`apply_revision`**, which appends an
immutable `creative_design_revision` and atomically advances the head.
This single mechanism provides undo/redo, version history, branching, A/B
testing, approval workflows, and team collaboration. Present from CS1, not
a future enhancement.

> **Corollary (Editability Invariant):** every creative is an editable
> layer document (`creative_design`) first; the rendered file is an output
> cache. No path from brief → `creative_asset` may bypass a design.

---

## FINAL ACCEPTANCE TEST

Before shipping any page, every answer must be YES:

1. Would a first-time business owner understand this?
2. Does it explain business impact?
3. Does it recommend an action?
4. Does it explain expected results?
5. Does it answer what is happening?
6. Does it answer what should I do?
7. Does it answer what result can I expect?

**If any answer is NO: DO NOT SHIP. REDESIGN FIRST.**

---

# OPERATIONAL DETAILS (the Constitution made implementable)

These sub-sections are the engineering / design contracts that make the Constitution above concrete. They never override the Constitution; they exist so engineers can implement it consistently.

## Plain-language translation table (canonical wording)

| ❌ Don't lead with | ✅ Lead with |
|---|---|
| CTR = 3.2% | 3 out of every 100 people clicked your ad. |
| ROAS = 4.5× | For every ₹1 spent on ads, you're earning ₹4.50 back. |
| CPC = ₹12 | You spend about ₹12 to bring one visitor to your business. |
| Conversion rate = 7% | About 7 of every 100 visitors became leads. |
| Bounce rate = 65% | Most visitors left without exploring — your landing page may need a stronger hook. |
| Sessions = 1,000 | About 1,000 people visited your business this period. |
| CPL = ₹120 | You spend ₹120 to get one potential customer. |
| CAC = ₹800 | You spend ₹800 to gain one paying customer. |

## Three-question worked examples by surface

| Surface | Q1 — What is happening? | Q2 — What should I do? | Q3 — What result can I expect? |
|---|---|---|---|
| Dashboard | What happened this week? | What should I do next? | What business impact will that have? |
| Leads | How many leads do I have? | Which leads should I contact first? | What revenue opportunity exists? |
| Campaigns | Which campaign is winning? | What should I optimise? | What improvement can I expect? |
| SEO | What is hurting my rankings? | What should I fix? | What traffic increase is possible? |
| Trends | What's gaining attention in my industry? | What content should I make? | How much engagement is likely? |
| Content / Ads / Visuals | What was generated? | Which variant should I publish? | What outcome does each variant predict? |
| Analytics | How is my business performing? | Which lever should I pull? | How much will it move the result? |

## 5-category Business Impact taxonomy

| Category | Plain-language frame | Example |
|---|---|---|
| **Revenue Impact** | money the business earns / loses | "Could add ₹15,000–₹25,000 in revenue this month" |
| **Lead Impact** | people expressing interest | "Likely 8–15 additional leads this week" |
| **Customer Impact** | converted, paying customers | "May convert 2–4 more customers" |
| **Time Impact** | hours saved or required | "Saves about 3 hours/week of manual posting" |
| **Cost Impact** | money the business spends / saves | "Reduces cost-per-lead by roughly ₹40" |

If a metric does not map to one of these five, it does not belong on a user-facing screen — it belongs in `[Show technical details]` or Professional Mode.

## AI confidence calibration (rough bands)

| Band | Label | Meaning | UI tone |
|---|---|---|---|
| 80–100 | High | Strong supporting data, recent + relevant | Primary CTA, suggest action by default |
| 60–79 | Medium | Reasonable data but with caveats | Suggest action, surface caveat |
| 40–59 | Low | Limited data or noisy signal | Frame as "worth trying" experiment |
| <40 | Speculative | Inference, weak signal — don't ship a CTA | Hide the recommendation OR frame as exploratory question |

Recommendations below 40% confidence should generally **not** ship as a CTA — they are guesses. Either gather more data first or surface as a question ("Want us to test this?") instead of an instruction.

## Currency

**Never hardcode INR.** Use the business / account currency. Resolve once per request from `business_profile` (location → ISO currency map). Pass the resolved currency to every AI prompt and every metric formatter, so plain-language explanations match what the user actually earns / spends.

Examples: India → INR, USA → USD, UK → GBP, UAE → AED.

## `<BusinessMetric>` component contract (Phase 2 deliverable)

Single reusable React component carrying the full Constitution contract:

```ts
{
  value:           string         // e.g. "₹120 per lead"
  plainLanguage:   string         // e.g. "You spend ₹120 to get one potential customer"
  status:          "good" | "warning" | "bad" | "neutral"
  impactCategory:  "revenue" | "lead" | "customer" | "time" | "cost"  // REQUIRED
  businessImpact:  string         // category-appropriate line
  recommendation:  string
  expectedResult:  string         // ranged when uncertain
  confidence:      0..100
  reason:          string         // ≤140 chars, what data this drew on
  technicalDetails?: Record<string, string | number>  // CTR/CPC/ROAS — disclosure only
}
```

Plus a sibling `<AiRecommendation>` for standalone recommendations not tied to a metric (e.g. the AI Coach card), carrying just `{ recommendation, expectedResult, confidence, reason }`.

The `impactCategory` is required — drives icon, accent colour, and grouping when multiple metrics render together. Components must refuse to render if any required field is missing.

## Backend recommendation contract

Every LLM response schema that produces a user-facing recommendation must include:

```python
recommendation: str
expected_result: str             # ranged when uncertain ("+10 to +20 leads")
confidence: int = Field(ge=0, le=100)
reason: str                      # one line, ≤140 chars
```

Backends must refuse to ship a recommendation that's missing any of these four fields.

## Implementation order — incremental, never big-bang

Apply this Constitution to existing surfaces one at a time, preserving functionality at every step.

| Phase | Scope | Why this order |
|---|---|---|
| **Phase 1** | **AI Coach reliability** — fix the LLM-call failure that currently triggers the deterministic fallback. The advisor's voice must actually work before anything else built on top of it is honest. | Coach IS the product. |
| **Phase 2** | **`<BusinessMetric>` + `<AiRecommendation>` reusable components** carrying the full Constitution contract above. One implementation, then mechanical reuse. | Without these, Phases 3–5 each reinvent the same pattern AND can't enforce the contract. |
| **Phase 3** | **Refactor `/analytics`** using `<BusinessMetric>`. Replace the 13-tile raw-metric wall with ≤5 plain-language tiles + AI summary, technical details behind disclosures. | Highest-impact violation today. |
| **Phase 4** | **Refactor `/trends`** — business-language framing on every insight, every topic carries cause + action + expected result. | High visibility, currently shows raw `relevance_score`. |
| **Phase 5** | **Refactor generator result cards** (`/content`, `/ads`, `/visuals`, `/campaigns`) — each result carries "what this means for your business" + action + expected result. | Touches every studio; do last because it's the broadest surface. |

Do not redesign everything at once. Each phase ships independently with tests + a working preceding state.

---

## Architectural principles

1. **Async-first.** Every LLM/image/network call goes through the job queue (Arq). FastAPI route handlers stay under 1s.
2. **Structured outputs everywhere.** No free-text LLM responses persisted to the DB. Every prompt has a Pydantic response schema; the LLM router validates.
3. **One LLM router.** All model calls go through `apps/api/aicmo/llm/router.py`. Never instantiate provider SDKs directly in feature modules.
4. **Modular backend.** Each domain (`onboarding`, `trends`, `content`, `ads`, `images`, `calendar`, `analytics`) is a self-contained package under `apps/api/aicmo/modules/` with its own router, service, schemas, models.
5. **Shared types via OpenAPI.** The frontend consumes types generated from FastAPI's OpenAPI schema — do not hand-write API types in the web app.

## What lives where

- Business-profile data and any user-owned content → Postgres.
- LLM call traces and cost telemetry → Postgres (`llm_traces` table).
- Vector retrieval is **not** in MVP. Don't add Pinecone/Weaviate until competitor analysis or RAG-based content lands.
- Static assets / generated images → S3 (post-MVP). For now, local filesystem + signed URLs are fine.

## Coding standards

- Backend: Ruff (lint+format), Pyright (type-check), Pydantic v2 models for all I/O.
- Frontend: ESLint, TypeScript strict mode, shadcn/ui primitives — never raw `<button>` etc. for app surfaces.
- Don't add comments that restate what the code does. Only comment non-obvious *why*.

## Adding a feature module (backend)

```
apps/api/aicmo/modules/<name>/
  __init__.py
  router.py     # FastAPI APIRouter
  service.py    # Business logic (pure functions / classes)
  schemas.py    # Pydantic request/response models
  models.py     # SQLAlchemy ORM models
  prompts.py    # LLM prompts + structured-output schemas
  tasks.py      # Arq job definitions
```

Then register the router in `aicmo/main.py` and the ORM models in `aicmo/db/base.py`.

## AUTH_MODE feature flag

The system supports three product modes via a single env flag:

| Mode | Backend | Frontend | Use case |
|---|---|---|---|
| `demo` | Every request → demo-user. Clerk env vars unused. | `<ClerkProvider>` not mounted. Sign-in/up render "Demo mode" fallback. Middleware pass-through. | Pure demo. No real auth anywhere. |
| `clerk` | Strict — missing/invalid JWT → 401. Refuses to boot without Clerk env. | `<ClerkProvider>` mounts. Real `<SignIn>`/`<SignUp>`. Middleware `auth.protect()` on non-public routes. | Production. Real users only. |
| `hybrid` (default) | No `Authorization` → demo-user. Valid Bearer → real Clerk user. Refuses to boot without Clerk env. | `<ClerkProvider>` mounts. Real sign-in works. Middleware mounts Clerk session BUT does NOT enforce auth. UserMenu shows `<UserButton>` when signed in, "Sign in" link when anonymous. | Public demo + real sign-in coexist. Landing → Open Dashboard works anonymously, /sign-in produces a real session. |

### Setting the mode

Both sides must agree:

```bash
# Root .env (backend reads via pydantic-settings)
AUTH_MODE=hybrid

# apps/web/.env.local (Next.js reads from per-app file)
NEXT_PUBLIC_AUTH_MODE=hybrid
```

Both `clerk` and `hybrid` require real Clerk env vars set on both sides AND a restart of both `uvicorn` (caches `Settings` in `lru_cache`) and `pnpm dev` (bakes `NEXT_PUBLIC_*` into the dev-server output at start).

### Source of truth

- `apps/api/aicmo/config.py:Settings.auth_mode` — backend
- `apps/api/aicmo/auth/clerk.py:require_user` — branches on mode
- `apps/api/aicmo/auth/clerk.py:assert_auth_config_valid` — startup guard
- `apps/web/src/lib/clerk-config.ts:getAuthMode` / `isDemoMode` / `isClerkActive` — frontend predicates
- `apps/web/src/middleware.ts` — inlines mode check (edge bundle)

### Boot guard

`assert_auth_config_valid()` runs at backend module load. It raises `SystemExit` if `AUTH_MODE=clerk` but `CLERK_JWT_ISSUER`/`CLERK_JWKS_URL` are placeholders or empty. This is the single defence against a misconfigured deploy that thinks it's running real auth but silently lets everything through. Pinned by `tests/test_auth_mode.py::TestClerkMode::test_startup_assert_refuses_without_clerk_config`.

### Component behaviour matrix

| Component | demo | clerk | hybrid |
|---|---|---|---|
| `<ClerkProvider>` | not mounted | mounted | mounted |
| `<SignIn>` / `<SignUp>` | "Demo mode" fallback | real Clerk UI | real Clerk UI |
| Middleware | pass-through | `auth.protect()` on non-public | Clerk session only, no protect |
| `<ClerkTokenBridge>` | dormant | wires `getToken` → `Authorization` | wires `getToken` (null when anon) |
| `<UserMenu>` | "Demo mode" badge | `<UserButton>` | `<UserButton>` if signed in, "Sign in" link if anon |
| TenantProvider | reads demo-user `/me` | reads real user `/me` | reads demo-user `/me` if anon, real user if signed in |
| OrgSwitcher / RoleBadge / BrandSwitcher | work against demo data | work against real user data | work against whichever user resolved |
| `/api/v1/**` routes | all serve demo-user | all serve real verified user | serve demo-user if anon, real if Bearer present |

All Clerk integration code is intact across all three modes — the flag only changes which branch executes at request time.

## Multi-tenancy (A3)

Every authenticated request carries a tenant. Backend resolves it from
two headers; the frontend is responsible for sending them.

### Backend contract

- Routes depend on `require_tenant()` or `require_permission(slug)` from
  `aicmo/tenancy/dependencies.py`. Those return a frozen `TenantContext`
  with `user_uuid`, `organization_id`, `brand_id`, `role_slugs`, and
  `permissions`.
- Headers:
  - `X-Organization-Id` — required when the user has > 1 active membership.
  - `X-Brand-Id` — required for brand-scoped routes when the org has > 1 brand.
- Auto-resolve: single membership → the org. Single brand → the brand.
  Backend also remembers `last_active_brand_id` per member so a returning
  user lands in the same brand without sending the header.
- Every service module filters by `brand_id` (and `organization_id` for
  org-level data). Never `WHERE user_id = …`.
- `bind_tenant_context` (in the resolver) mirrors the tenant into both
  structlog contextvars and Sentry tags. Every downstream log + Sentry
  event carries `user`, `organization_id`, `brand_id`, `role`.

### Frontend contract

- `<TenantProvider>` wraps the `(app)` route group in
  `apps/web/src/app/(app)/layout.tsx`. It:
  1. Reads the persisted `{org, brand}` from localStorage (key
     `aicmo.tenant.selection.v1`).
  2. Calls `GET /api/v1/users/me`, which returns memberships + the backend's
     resolved active tenant.
  3. Picks the active org/brand (persisted preference → backend's
     `active` field → first membership / brand).
  4. Mirrors the resolved IDs into the `lib/tenant.ts` header cache,
     localStorage, and Sentry tags.
  5. Honors `suggested_route` from the backend (e.g. zero memberships
     → `/onboarding/org`).

- `useTenant()` is the consumer hook. Returns:
  - `status`: `loading | ready | error | no-memberships`
  - `user`, `activeOrg`, `activeBrand`, `activeMembership`, `memberships`
  - `permissions`, `roleSlugs`, `can(slug)`, `canAll([...])`, `canAny([...])`
  - `environment` — for UI badges
  - `switchOrg(id)`, `switchBrand(id)`, `refresh()`
  - `active` — the backend's last-resolved snapshot (for debug surfaces)

- Tenant headers on outbound calls: `lib/api.ts:request()` reads from
  the module-level cache (`getActiveTenantHeaders()` in `lib/tenant.ts`).
  Per-call override via `request(path, { organizationId, brandId })`.
  Pass `null` explicitly to suppress a header (used by `TenantProvider`'s
  initial `/me` call when no tenant is known yet).

- Permission gating in UI: use `useTenant().can("content.create")` rather
  than role-string comparisons. Roles change; permission slugs are stable.

### Adding a new tenant-scoped API method

Backend:
```python
@router.post("/api/v1/widgets")
async def create_widget(
    payload: CreateWidget,
    tenant: TenantContext = Depends(require_permission("content.create")),
    session: AsyncSession = Depends(get_db),
):
    return await widgets_service.create(
        session,
        brand_id=tenant.brand_id,
        organization_id=tenant.organization_id,
        ...
    )
```

Frontend: just call `api.widgets.create(payload)` — the active tenant
headers attach automatically.

### Testing

- Backend: `cd apps/api && .venv/bin/python -m pytest tests/`
- Frontend: `cd apps/web && pnpm test`
- Tenant-specific suites:
  - `apps/api/tests/tenancy/` — pure-function header + context invariants
  - `apps/web/src/lib/tenant.test.ts` — persistence, header cache, resolution
  - `apps/web/src/lib/api.test.ts` — header injection at the fetch boundary
  - `apps/web/src/components/tenant-provider.test.tsx` — provider lifecycle
  - `apps/web/src/components/org-switcher.test.tsx` — org switcher state matrix
  - `apps/web/src/components/brand-switcher.test.tsx` — brand switcher state matrix
  - `apps/web/src/components/role-badge.test.tsx` — role badge rendering
  - `apps/web/src/components/tenant-topbar.test.tsx` — composed topbar

### Tenant switcher UI (A4)

Topbar composition (`apps/web/src/components/tenant-topbar.tsx`):

```
[OrgSwitcher] · [BrandSwitcher] · [EnvironmentBadge] · [RoleBadge]
```

- **`OrgSwitcher`** — dropdown of `useTenant().memberships`. Collapses
  to a static label when the user has ≤1 membership. Click an option
  → `switchOrg(id)` → provider refetches `/me` with the new
  `X-Organization-Id` header → React state + Sentry tags + localStorage
  all update. Shows a spinner during the in-flight switch; surfaces a
  banner if `switchOrg()` rejects.

- **`BrandSwitcher`** — dropdown of `activeMembership.brands`. Same
  collapse + pending + error semantics. Returns `null` (not a label)
  when there's no active membership, because `OrgSwitcher` already
  communicates the empty-workspace state.

- **`EnvironmentBadge`** — surfaces `useTenant().environment`, which is
  resolved at build time from `NEXT_PUBLIC_APP_ENV` /
  `NEXT_PUBLIC_SENTRY_ENVIRONMENT` / `NODE_ENV`. Production gets a
  destructive-tone border so it's impossible to mistake for staging.

- **`RoleBadge`** — primary role on the active org (alphabetically
  first slug — same selection the backend uses for log/Sentry tagging).
  Renders nothing while loading or when the user has no roles. The
  tooltip lists all roles when there are multiple.

#### Switch flow (sequence)

```
user clicks Org Two            ⟶ OrgSwitcher.handleSwitch("org-2")
                               ⟶ TenantProvider.switchOrg("org-2")
                                 1. setActiveTenantHeaders({ org_id: "org-2", brand_id: null })
                                 2. await api.me({ organizationId: "org-2" })
                                    ⟶ backend require_tenant validates membership
                                      • TenantMismatch if not a member (403)
                                      • Resolves brand from last_active_brand_id or auto-resolve
                                 3. setActiveTenantHeaders({ org_id, brand_id }) — resolved
                                 4. writePersistedSelection({ org_id, brand_id })
                                 5. setSentryTenant({ user, org, brand, role })
                                 6. setState(me)  ← React tree re-renders
                                 7. router.push(suggested_route) if mismatch
```

#### Security assumptions

1. **No client-side authority.** The switcher only allows selecting orgs
   from `useTenant().memberships`. That list comes from
   `GET /api/v1/users/me`, which the backend builds from
   `OrganizationMember WHERE user_id = $clerk_user_uuid`. The frontend
   cannot fabricate a membership.

2. **Server re-validates every request.** Even if a tampered client sent
   `X-Organization-Id: <some-org-the-user-isnt-in>`, the backend's
   `require_tenant` calls `_load_active_member(user_id, org_id)` and
   raises `TenantMismatch` (403). The UI is *not* the trust boundary.

3. **Brand validity is checked too.** `require_tenant` enforces
   `brand.organization_id == active_org_id` and `brand.status == "active"`.
   A switcher item for a deleted/wrong-org brand fails closed on the
   next request.

4. **Persistence is preference, not authority.** localStorage stores
   `{organization_id, brand_id}` only as a hint. Backend re-validates on
   every cold load — stale persisted IDs degrade gracefully to "fall
   back to first membership" via `resolveActiveMembership` in
   `lib/tenant.ts`.

5. **Stale `activeOrg` doesn't leak via UI labels.** Single-membership
   collapse renders `memberships[0].organization.name`, not
   `activeOrg.name`, so a ghost activeOrg (deleted org still in state)
   cannot show up as the workspace label.

6. **Pending state blocks concurrent switches.** While `switchOrg` is
   in-flight, all other menuitems are `disabled` — prevents a
   double-click race that could leave the headers ahead of the React
   state.

## End-to-end tenant lifecycle (A5)

### The full request flow

```
┌──────────────────┐
│ user opens app   │
└────────┬─────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Clerk SDK auto-redirects to /sign-in if no session               │
│ (apps/web/src/components/auth-provider.tsx — ClerkProvider)      │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Clerk sets session cookie + injects JWT on outbound calls        │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Next.js renders (app)/layout.tsx                                  │
│   → <TenantProvider enforceSuggestedRoute>                        │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ TenantProvider effect (on mount):                                 │
│   1. readPersistedSelection() ← localStorage                      │
│   2. setActiveTenantHeaders({org, brand})  [optimistic]           │
│   3. api.me({organizationId, brandId})                            │
│                                                                    │
│ → outbound: GET /api/v1/users/me                                        │
│   Headers:                                                         │
│     Authorization: Bearer <clerk JWT>                              │
│     X-Organization-Id: <persisted or null>                         │
│     X-Brand-Id:        <persisted or null>                         │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI: require_user (Clerk JWT verify)                          │
│   → AuthContext{user_id (Clerk sub), session_id, org_id, claims}  │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI: require_tenant (in users/router.py — called manually     │
│   by /me because /me must never 4xx for an authed user)           │
│                                                                    │
│   1. _get_or_create_user(clerk_user_id)                           │
│   2. parse_org_header()  → uuid or None                           │
│      • garbage → MissingTenant (400)                              │
│   3. resolve org:                                                  │
│      • header present → _load_active_member(user, org)            │
│        → None ⇒ TenantMismatch (403)                              │
│      • no header → _single_active_membership_org()                │
│        → None ⇒ MissingTenant (400)                               │
│   4. session.get(Organization, org_id)                            │
│      • status != "active" ⇒ OrganizationInactive (403)            │
│   5. parse_brand_header() / member.last_active_brand_id           │
│      / _only_active_brand()                                       │
│   6. validate: brand.organization_id == org_id                    │
│      • mismatch ⇒ BrandNotInOrg (403)                             │
│      • inactive ⇒ BrandInactive (403)                             │
│   7. compute_permissions_for_member()                             │
│      compute_role_slugs_for_member()                              │
│      → SQL: MemberRole ⨝ RolePermission ⨝ Permission              │
│   8. bind_contextvars + bind_tenant_context (structlog + Sentry)  │
│   9. return frozen TenantContext                                  │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ build_me_response() — joins memberships → orgs → brands → roles   │
│ → MeResponse{user, memberships[], active, suggested_route}        │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ TenantProvider receives MeResponse:                               │
│   1. resolveActiveMembership(me, persistedOrg)                    │
│   2. resolveActiveBrand(membership, persistedBrand)               │
│   3. setActiveTenantHeaders({resolved})  [persist]                │
│   4. writePersistedSelection({resolved})                          │
│   5. setSentryTenant({user, org, brand, role})                    │
│   6. setMe(resp); setActiveOrgId(); setActiveBrandId()            │
│   7. status = "ready"                                             │
│   8. if enforceSuggestedRoute && current != suggested_route       │
│      → router.push(suggested_route)                               │
└────────┬─────────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ React tree re-renders.                                            │
│ <TenantTopbar> reads useTenant() → renders switchers.             │
│ Feature pages read useTenant().can(slug) → gate UI per perm.      │
└──────────────────────────────────────────────────────────────────┘
```

### What happens on every subsequent API call

```
ComponentX calls api.widgets.list()
  → request("/api/v1/widgets")
      → reads getActiveTenantHeaders() from lib/tenant.ts module state
      → attaches X-Organization-Id + X-Brand-Id
  → fetch()
      → FastAPI router: Depends(require_permission("widgets.read"))
          → require_tenant() (re-resolves on every request — no caching
            between requests; cheap because /me-style joins aren't run,
            only the per-request lookups)
          → permission check
      → service queries with brand_id filter
  ← 200 with the brand-scoped data
```

### What happens on switch

```
User clicks OrgSwitcher → handleSwitch(org-2)
  → TenantProvider.switchOrg("org-2")
      1. setActiveTenantHeaders({org: "org-2", brand: null})  [optimistic]
      2. await loadMe({organizationId: "org-2"})
          → api.me({organizationId: "org-2"})  ← uses override, not cache
              → GET /api/v1/users/me with X-Organization-Id: org-2
              → backend re-validates membership → resolves brand → returns
          → resolve, persist, update Sentry, setState
  ← React re-renders with new active tenant
  ← Topbar updates, permission-gated UI re-evaluates
```

### Trust boundaries

The system has three layers of authority — only ONE of them is trusted:

| Layer | Trusted? | Why |
|---|---|---|
| Frontend React state | ❌ No | Anything in `useTenant()` is display-only. An attacker with devtools can mutate React state without consequence — the backend re-validates every header on every request. |
| Persisted selection (localStorage) | ❌ No | A preference, not authority. Resetting it logs the user out of nothing; tampering with it just sends a different header that the backend then validates. |
| HTTP headers from the client | ❌ No | Assumed adversarial. `parse_org_header` accepts only well-formed UUIDs; `require_tenant` queries the DB to confirm membership. |
| Backend `require_tenant` + DB | ✅ Yes | The only source of truth. Every protected route depends on it; permissions come from the `MemberRole ⨝ RolePermission ⨝ Permission` join, not from any client input. |

### Security guarantees (with test pins)

Each guarantee maps to a test in `apps/api/tests/tenancy/test_security_invariants.py`:

| # | Guarantee | Test class |
|---|---|---|
| 1 | Users cannot access orgs outside their memberships | `TestNoAccessOutsideMemberships` |
| 2 | Users cannot access brands outside the active org | `TestNoCrossOrgBrandAccess` |
| 3 | Header tampering is rejected | `TestHeaderTampering` |
| 4 | Tenant isolation enforced (resolver returns ONE brand_id) | `TestTenantIsolation` |
| 5 | Role escalation impossible from frontend | `TestNoRoleEscalation` |
| 6 | Refresh preserves trust without privilege gain | `TestRefreshIntegrity` |

### Known limitations (as of A5)

1. **No Postgres-backed integration suite.** Tenant resolver tests use
   stubbed `AsyncSession`. The resolver's SQL has been validated
   manually + via the running app, but is not in CI. Tracked: backend
   testing-infra backlog.
2. **No middleware-level tenant assertion.** All tenant checks happen
   in route dependencies. A new route that forgets `Depends(require_tenant)`
   would be authenticated but unscoped. Tracked: lint rule to require
   `tenant: TenantContext` on every router under `/api/v1` except the
   public ones.
3. **No tenant scope on Arq background jobs yet.** When a job picks up
   work, it doesn't inherit the calling request's tenant. Current jobs
   pass `brand_id` explicitly through their payload, which is correct
   but verbose. Tracked: extend `bind_tenant_context` for Arq workers.
4. **Sentry tagging only when SDK initialised.** `bind_tenant_context`
   is a no-op when `SENTRY_DSN` is empty (correct dev default). If a
   prod env forgets the DSN, capture works but events lack tenant tags.
   The `/api/v1/debug/sentry-config` endpoint (A2) is the operational
   guard.
5. **Org/brand switcher UI is text-only.** No avatar / favicon for orgs;
   no color tagging for brands. Cosmetic only — doesn't affect security.
6. **No org-switcher in middleware.** The redirect-on-`suggested_route`
   happens client-side after `/me` returns. A hard-reload to a brand-
   scoped URL before `/me` resolves shows the page's loading state,
   not a tenant-resolved page. Acceptable for current UX; revisit if
   first-paint metrics get measured.

### Smoke test inventory

| Suite | File | Tests | What it proves |
|---|---|---|---|
| Frontend integration | `apps/web/src/__smoke__/tenant-lifecycle.smoke.test.tsx` | 5 | Cold boot, switch end-to-end, persistence survives remount, backend-rejection surfaces as error, role-based rendering reacts to switch |
| Backend resolver | `apps/api/tests/tenancy/test_resolver_smoke.py` | 7 | Auto-resolve, non-member rejection, malformed header, cross-org brand, inactive org, permission deny, permission allow |
| Backend security | `apps/api/tests/tenancy/test_security_invariants.py` | 10 | Pinned-test-per-guarantee for the 6 security properties |

## Onboarding wizard (W1-15)

### When it runs

A newly-authenticated user with zero memberships lands on `/dashboard`
(or wherever) → `<TenantProvider enforceSuggestedRoute>` reads `/me`,
sees `suggested_route="/onboarding/org"`, and pushes them to the wizard.
The wizard route is *outside* the `(app)` group so the sidebar +
TenantProvider don't render around it.

### Onboarding lifecycle

```
sign-up via Clerk
    ▼
Clerk session set, JWT issued
    ▼
GET /api/v1/users/me              ← TenantProvider boots
    backend: lazy-create User row
    response: memberships=[], suggested_route="/onboarding/org"
    ▼
router.push("/onboarding/org")    ← provider's enforceSuggestedRoute
    ▼
OnboardingWizard mounts (outside (app), no sidebar, no provider)
  ├─ step 1: organization name + slug
  │            slug auto-derived via lib/slugify.ts until user edits it
  ├─ step 2: brand name + slug (same auto-derive behaviour)
  ├─ step 3: display name (optional); role shown as "Owner"
  └─ step 4: review
        ▼
POST /api/v1/orgs/workspace       ← single transactional call
    ▼
backend create_workspace():
    1. user.display_name = payload.display_name (if provided)
    2. INSERT organization        (unique slug check)
    3. INSERT brand               (unique-per-org slug check)
    4. INSERT organization_member
    5. SELECT role.id WHERE slug='owner' AND is_system=true
    6. INSERT member_role
    7. INSERT 3 audit rows
    session.commit()  ← all-or-nothing
    ▼
201 → OnboardingWorkspaceResult
    ▼
Wizard:
  - writePersistedSelection({org_id, brand_id})  ← seed for cold boot
  - clearPersistedWizard()                       ← drop draft
  - router.push("/dashboard")
    ▼
(app)/layout.tsx mounts → TenantProvider boots → /me returns the new
membership → topbar renders with org/brand → ready to use the product
```

### Entity creation order

Every step is inside ONE Postgres transaction:

| # | Entity | Source of values | Notes |
|---|---|---|---|
| 0 | `users.display_name` UPDATE | step 3 (optional) | First so a later failure rolls back this rename too |
| 1 | `organizations` INSERT | step 1 | Unique constraint on `slug` (global) — duplicate → 409 + rollback |
| 2 | `brands` INSERT | step 2 | Partial unique index on `(organization_id, slug)` among non-deleted — duplicate → 409 + rollback |
| 3 | `organization_members` INSERT | derived | `last_active_brand_id` set to the brand from step 2 so first `/me` carries it |
| 4 | `member_roles` INSERT | system | `role.slug='owner'`, `is_system=true` |
| 5 | `audit_logs` × 3 | derived | `organization.created`, `brand.created`, `member.role_assigned` — all tagged `via=onboarding_wizard` |

### Ownership model

- The authenticated user (from Clerk JWT, then lazy-created in `users`)
  is `org.owner_user_id`. Always. No way to specify another user.
- That same user is assigned the `owner` system role on the new member
  row. `MemberRole.assigned_by_user_id = self` — explicit self-grant,
  the only place self-grant of Owner is permitted.
- Subsequent role grants/transfers go through `orgs/service.assign_role`
  which enforces "only an existing Owner can grant Owner".

### Failure handling

| Failure | HTTP | Frontend behavior | DB state |
|---|---|---|---|
| Validation error on payload | 422 | Wizard surfaces `submitError` inline; user edits + retries; state preserved in localStorage | unchanged |
| Duplicate org slug | 409 | Same — message contains the offending slug | rollback (no rows inserted) |
| Duplicate brand slug | 409 | Same | rollback (org INSERT also reverted) |
| Network error | thrown `Error` | Generic message; retry on next click | unchanged |
| Owner role missing in DB | 500 | Inline message; ops alert via Sentry | rollback |

### Security properties (pinned by `tests/onboarding/test_workspace_service.py`)

1. **Owner-on-create is always the caller.** `org.owner_user_id` and
   `member_role.assigned_by_user_id` are both set from the authed user
   — never from the request body.
2. **No tenant-header bypass.** The endpoint runs with no tenant
   headers expected (the user has no tenant yet). `api.onboarding.createWorkspace`
   passes `organizationId: null, brandId: null` to explicitly suppress
   any stale cached headers from the module-level cache in `lib/tenant.ts`.
3. **Slug uniqueness enforced by DB, not app code.** `IntegrityError`
   on the first or second flush converts to a clean 409. Race condition
   between two concurrent wizard submits with the same slug → second
   one fails cleanly.
4. **All-or-nothing.** If brand INSERT fails after org INSERT succeeds,
   the org INSERT is rolled back. No half-created tenants.
5. **Persisted wizard state is preference, not authority.** The
   localStorage draft never gets sent to the backend as-is — only the
   in-memory React state, which the user has actively confirmed by
   advancing through the steps.

### Wizard UX details

- **Resume**: `localStorage["aicmo.onboarding.wizard.v1"]` snapshots the
  state on every change. A tab close, refresh, or accidental nav restores
  the same step + values on remount.
- **Slug auto-derivation**: typing in `name` populates `slug` (via
  `lib/slugify.ts`) until the user manually edits the slug — after
  that, the auto-fill is suppressed for that slug field.
- **Mobile-friendly**: `max-w-2xl mx-auto p-4 sm:p-8` keeps the form
  centered + readable on phones; inputs stack naturally.
- **Progress indicator**: 4 pill bars with `data-active` / `data-done`
  attributes so future styling (e.g. animated transitions) hooks cleanly.
