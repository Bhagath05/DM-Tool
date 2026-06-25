# Phase 10.3 — Founder Simplification Pass

**Status:** Design approved (founder directive 2026-06-08). Implementation in progress.
**Owner:** Frontend nav + page reshape. **Zero backend touch.**
**Constitution anchor:** [`CLAUDE.md`](../CLAUDE.md) — "If a first-time business
owner cannot understand a page within 10 seconds, the design fails."

---

## Mission

Transform DM Tool from a **feature-oriented dashboard** into an
**AI Growth Operating System** — a founder's daily command center that
answers "what should I do next to get more customers?"

A first-time business owner should know exactly where to go within **10 seconds**.

---

## Hard constraints (per founder directive)

This is a **product restructuring** phase, not a feature-building phase.

| Forbidden | Why |
|---|---|
| ❌ New business logic | Restructure existing behaviour, don't add to it |
| ❌ Backend contract changes | Every API stays as-is |
| ❌ API endpoint additions / mods | Frontend uses what's already there |
| ❌ Permission / RBAC changes | Tenant model untouched |
| ❌ Database schema changes | No migrations in this phase |
| ❌ Changes to billing / team / security / notifications / analytics / AI Coach / Performance Intelligence engines | Pure restructuring — these systems keep working untouched |
| ❌ Feature removal | Every existing feature stays reachable (direct URL, command palette, or Advanced Mode) |
| ❌ Broken routes | Every legacy URL keeps resolving (308 redirects) |

**Allowed:**

- ✅ Frontend route additions (Next.js page files)
- ✅ Frontend redirect stubs
- ✅ Component recomposition (recomposing existing components into new pages)
- ✅ UI label renames
- ✅ Sidebar / command-palette refactor
- ✅ Client-side preference (localStorage) for Advanced Mode

---

## 1. Current state

**17 destinations** in primary surface. 4 collapsible groups + a "More" tray.
Plus 7 sub-routes inside Settings.

```
Overview         Growth                Creative      Workspace    More
─────────        ──────                ────────      ─────────    ────
Overview         Campaigns             Content       Settings     Trends
Performance      Leads                 Ads                        Bundles
AI Coach         Opportunities         Visuals                    Lead pages
                 Analytics             Library                    Social signals
                                                                  Campaign lab
```

**Concepts a founder has to learn:** 16 distinct nouns
(Overview, Performance Intelligence, AI Coach, Campaigns, Leads, Opportunities,
Analytics, Content, Ads, Visuals, Library, Trends, Bundles, Lead pages,
Social signals, Campaign lab).

**Already-collapsed legacy routes** (308 redirects, invisible to nav):
`/dashboard`, `/today`, `/organization`, `/team`, `/billing`.

---

## 2. Founder Journey — the five questions

### Q1. What should the user see first?

**Today's Plan.** Answers the three Constitution questions in this order:

1. **What should I do today?** → ONE hero action, highest confidence.
2. **What is happening?** → glance row: leads waiting · posts to publish · plan progress.
3. **What changed?** → 1–2 deltas + 1 new opportunity.

### Q2. What should the user do first?

The single action that creates **revenue fastest**. Picked by the existing
weekly-plan engine (`api.coach.weekly`), ranked by
`confidence × business_impact_category_weight` (Revenue > Lead > Customer >
Time > Cost).

### Q3. What actions create business value fastest?

| Rank | Action | New home |
|---|---|---|
| 1 | Contact a warm lead | `/grow/leads` |
| 2 | Publish planned content | `/today` (CTA) → `/create/content` |
| 3 | Approve AI recommendation | `/today` (hero card) |
| 4 | Launch a lead-gen page | `/grow/leads` (tab) |
| 5 | Act on a new opportunity | `/grow/opportunities` |

### Q4. Which pages are unnecessary in primary nav?

| Page | Why | New home |
|---|---|---|
| Library | Asset history — pulled, not browsed | Advanced Mode |
| Trends | Raw signal — already feeds Opportunities | Advanced Mode |
| Bundles | Workflow tool — belongs inside Content | `/create/content` |
| Lead pages | Asset type — belongs inside Get More Leads | `/grow/leads` |
| Visuals | Creative type — belongs inside Content | `/create/content` (tab) |
| Campaign Lab | Power-user A/B experiment tool | Advanced Mode |
| AI Coach (own page) | Same content as Today's Plan, deeper | "See all actions" link on Today |
| Overview | Page is fine — NAME is passive | Renamed → "Today's Plan" |
| Analytics + Performance | Two analytics pages confuse | Merged → `/results` |
| Campaigns (calendar) | Founders think in days, not campaigns | This-week strip inside Today |

### Q5. Which pages live behind Advanced Mode?

Three pages, gated by `users.preferences.advanced_mode` (boolean,
default `false`):

- **Campaign Lab** — experiment design, learning loop
- **Library** — full asset history with filters
- **Trends (raw feed)** — unfiltered trend list

When Advanced Mode is off, these don't appear in the sidebar. Direct URLs
still resolve (no 404) so power-user bookmarks + docs links work.

---

## 3. Simplified IA — the new model

**5 sections, 8 primary destinations** (down from 17 → 53% reduction).

```
┌──────────────────────────────────────────────────────┐
│ TODAY                                                │
│   • Today's Plan                              /today │
│                                                      │
│ GROW                                                 │
│   • Leads                                /grow/leads │
│   • Opportunities                /grow/opportunities │
│   • Market Intelligence  /grow/market-intelligence   │
│                                                      │
│ CREATE                                               │
│   • Social Posts             /create/social-posts    │  ← was /content
│   • Ads                              /create/ads     │
│   • Creatives                /create/creatives       │  ← was /visuals
│                                                      │
│ RESULTS                                              │
│   • Performance                            /results  │  ← merges /performance + /analytics
│                                                      │
│ SETTINGS                                             │
│   • Workspace                            /settings   │
└──────────────────────────────────────────────────────┘
        (Advanced Mode toggle → adds in sidebar:
         Library · Campaign Lab · Trends raw feed)
```

### Concept count: 16 → 8

`Today's Plan · Leads · Opportunities · Market Intelligence · Social Posts · Ads · Creatives · Performance`

Every word means something to a founder who has never opened a marketing tool.

### Plain-language renames

| Old | New | Why |
|---|---|---|
| Overview | **Today's Plan** | Action-first, time-anchored |
| Trends + Social Signals (+ Audience) | **Market Intelligence** | One unified intelligence center |
| Content | **Social Posts** | Founder language — they don't say "content" |
| Visuals | **Creatives** | Broader bucket; preps Pomelli integration |
| Performance Intelligence + Analytics | **Performance** | One word, one place |
| AI Coach (top-level) | (folded into Today) | Coach IS the plan |
| Campaigns (calendar) | (folded into Today's "This Week" strip) | Founders think days, not campaigns |

### Pages that lose their nav slot but keep working

Per "no feature removal" mandate, every existing route stays reachable:

| Route | How it stays reachable |
|---|---|
| `/library` | Advanced Mode sidebar · direct URL · command palette (advanced) |
| `/campaign-lab` | Advanced Mode sidebar · direct URL · command palette (advanced) |
| `/trends` | Direct URL · command palette (advanced) · default redirect to `/grow/market-intelligence` |
| `/campaigns` | Direct URL · command palette (search-only) |
| `/bundles` | Functionality inlined into `/grow/opportunities` |
| `/ai-coach` | Direct URL still works · "See all actions" link from `/today` |
| `/landing-pages` | Direct URL · accessed as a tab inside `/grow/leads` |

---

## 3a. Audit deliverables (per founder directive)

### (1) Current routes — every page that exists today

| Route | Purpose | Disposition in 10.3 |
|---|---|---|
| `/overview` | Big merged front door (8 sections) | Becomes redirect → `/today` |
| `/today` | Already a redirect → `/overview` | Becomes real page (slice 4) |
| `/dashboard` | Legacy redirect → `/overview` | Re-targets → `/today` |
| `/ai-coach` | Full weekly plan deep-dive | Direct URL only; folded summary on `/today` |
| `/performance` | Performance Intelligence (Phase 9.1.5) | Merged into `/results` (slice 6) |
| `/analytics` | Constitution-shaped analytics | Merged into `/results` (slice 6) |
| `/campaigns` | Calendar / planner | Removed from nav; direct URL preserved |
| `/leads` | Lead inbox with priority ranking | Renamed → `/grow/leads` |
| `/opportunities` | AI-surfaced opportunities | Renamed → `/grow/opportunities` |
| `/content` | Social post / caption generator | Renamed → `/create/social-posts` |
| `/ads` | Meta + Google ad generator | Renamed → `/create/ads` |
| `/visuals` | AI image generator | Renamed → `/create/creatives` |
| `/library` | Asset history | Advanced Mode only |
| `/trends` | Raw trend feed | Default redirect → `/grow/market-intelligence`; raw access via Advanced Mode |
| `/bundles` | Bundled-asset workflow | Inlined into `/grow/opportunities` |
| `/social` | Social signals / competitor analysis | Becomes a tab inside `/grow/market-intelligence` |
| `/landing-pages` | Lead-capture page builder | Becomes a tab inside `/grow/leads` |
| `/campaign-lab` | A/B learning experiments | Advanced Mode only |
| `/onboarding` | Conversational onboarding | Unchanged |
| `/settings/*` | 7 settings subroutes | Unchanged (Phase 10.1 shell preserved) |
| `/organization`, `/team`, `/billing` | Legacy redirects to `/settings/*` | Unchanged |

### (2) Current navigation — what the founder sees in the sidebar today

17 items spread across 4 groups + "More" tray. See Section 1.

### (3) Migration map — old URL → new URL

| Legacy URL | New URL | Type |
|---|---|---|
| `/dashboard` | `/today` | redirect |
| `/overview` | `/today` | redirect |
| `/ai-coach` | (unchanged, direct URL) | kept |
| `/today` | (becomes the real page) | reshape (slice 4) |
| `/leads` | `/grow/leads` | redirect |
| `/landing-pages` | `/grow/leads?tab=pages` | redirect (slice 1) → tab (slice 5+) |
| `/opportunities` | `/grow/opportunities` | redirect |
| `/bundles` | `/grow/opportunities` | redirect |
| `/social` | `/grow/market-intelligence` | redirect |
| `/trends` | `/grow/market-intelligence` (default) | redirect |
| `/content` | `/create/social-posts` | redirect |
| `/ads` | `/create/ads` | redirect |
| `/visuals` | `/create/creatives` | redirect |
| `/performance` | `/results` | redirect |
| `/analytics` | `/results` | redirect |
| `/library` | (unchanged, Advanced Mode) | kept |
| `/campaign-lab` | (unchanged, Advanced Mode) | kept |
| `/campaigns` | (unchanged, direct URL) | kept |

### (4) Reused pages — components carry over, no rewrites

| New page | Reuses | Notes |
|---|---|---|
| `/today` | `QuickWins`, `AiCoachPanel`, `ActionCenter`, `OverviewHero` | Recompose into the 4-section layout |
| `/grow/leads` | `Inbox` from `/leads/_components` | Add `/landing-pages` as a tab later |
| `/grow/opportunities` | `OpportunityCenter` from `/opportunities/_components` | Inline `/bundles` flow later |
| `/grow/market-intelligence` | Existing `/social` + `/trends` page components | Tabbed shell |
| `/create/social-posts` | Existing `/content` page | Pure rename initially |
| `/create/ads` | Existing `/ads` page | Pure rename |
| `/create/creatives` | Existing `/visuals` page | Pure rename |
| `/results` | `ExecutiveSummary`, `WinningCreativeFormula`, `PerformanceSection`, `IndustryBenchmark` from `/overview/_components` + existing `/performance` + `/analytics` page components | Hero summary + tabs |

### (5) Redirects — every URL that 308s to a new home

Implemented in `src/app/(app)/<legacy-path>/page.tsx` as a one-liner
`redirect()` call. Pattern identical to the existing `/dashboard` →
`/overview` legacy stub.

12 redirect stubs total:
`/leads → /grow/leads · /landing-pages → /grow/leads · /opportunities → /grow/opportunities · /bundles → /grow/opportunities · /social → /grow/market-intelligence · /trends → /grow/market-intelligence · /content → /create/social-posts · /ads → /create/ads · /visuals → /create/creatives · /performance → /results · /analytics → /results · /overview → /today`

### (6) Renamed destinations — label-level changes

These are pure UI string changes in sidebar + command palette. Page
content stays identical until later slices.

| Old label | New label |
|---|---|
| Overview | Today's Plan |
| AI Coach (nav slot) | (folded into Today) |
| Performance Intelligence | Performance |
| Analytics | (merged into Performance) |
| Leads | Leads (label same; URL becomes `/grow/leads`) |
| Opportunities | Opportunities |
| Social Signals | Market Intelligence |
| Trends (nav slot) | (folded into Market Intelligence) |
| Content | Social Posts |
| Ads | Ads |
| Visuals | Creatives |
| Library | Library (Advanced Mode only) |
| Campaign Lab | Campaign Lab (Advanced Mode only) |
| Campaigns | (removed from nav) |
| Lead Pages (nav slot) | (folded into Leads as tab) |
| Bundles | (folded into Opportunities) |

### (7) Final navigation structure — see Section 3 above

### (8) Implementation plan — see Section 6 below

---

## 4. Sidebar — before / after

### BEFORE

```
┌────────────────────────────────┐
│ ✨ DM Tool                     │
├────────────────────────────────┤
│ OVERVIEW              ▾        │
│   ▮ Overview                   │
│   ◌ Performance Intelligence   │
│   ◌ AI Coach                   │
│                                │
│ GROWTH                ▾        │
│   ◌ Campaigns                  │
│   ◌ Leads                      │
│   ◌ Opportunities              │
│   ◌ Analytics                  │
│                                │
│ CREATIVE              ▾        │
│   ◌ Content                    │
│   ◌ Ads                        │
│   ◌ Visuals                    │
│   ◌ Library                    │
│                                │
│ WORKSPACE             ▾        │
│   ◌ Settings                   │
│                                │
│ ▸ More                         │
│   (Trends, Bundles, Lead pages,│
│    Social signals, Camp. lab)  │
├────────────────────────────────┤
│ 🟣 ND  Nikhil D.               │
│        Acme · Default          │
│ ┌──────────────────────────┐   │
│ │ PLAN          Early Acc. │   │
│ └──────────────────────────┘   │
└────────────────────────────────┘
```

### AFTER

```
┌────────────────────────────────┐
│ ✨ DM Tool                     │
├────────────────────────────────┤
│ TODAY                          │
│   ▮ Today's Plan               │  ← the front door
│                                │
│ GROW                           │
│   ◌ Leads                      │
│   ◌ Opportunities              │
│   ◌ Market Intelligence        │  ← Trends + Social + Audience
│                                │
│ CREATE                         │
│   ◌ Social Posts               │  ← was Content
│   ◌ Ads                        │
│   ◌ Creatives                  │  ← was Visuals (prep Pomelli)
│                                │
│ RESULTS                        │
│   ◌ Performance                │  ← Performance + Analytics merged
│                                │
│ SETTINGS                       │
│   ◌ Workspace                  │
│                                │
│ ─── (advanced mode only) ───   │
│   ◌ Library                    │
│   ◌ Campaign Lab               │
│   ◌ Trends (raw feed)          │
├────────────────────────────────┤
│ 🟣 ND  Nikhil D.               │
│        Acme · Default          │
│ ┌──────────────────────────┐   │
│ │ PLAN          Early Acc. │   │
│ └──────────────────────────┘   │
└────────────────────────────────┘
```

### Advanced Mode — client-only, zero backend

The Advanced Mode toggle lives entirely in the browser. **No DB column, no
API endpoint.** This respects the "no schema changes" mandate AND has a
useful side effect: the preference is per-device (a founder on her laptop
keeps Advanced off; her engineer on his desktop keeps it on).

Implementation:

- `localStorage` key: `aicmo.preferences.advanced_mode.v1` (boolean).
- `useAdvancedMode()` hook in `src/lib/preferences.ts`.
- Sidebar consumes it via the hook; conditionally appends three items.
- Settings → Preferences page exposes a single toggle.
- Default: `false`. First-time visitors see only the 8 primary items.

---

## 5. Today's Plan page composition

Compresses the current 8-section Overview into **4 action-shaped sections**.

```
┌────────────────────────────────────────────────────────────────────┐
│  Good morning, Nikhil. Here's today.                Mon · Jun 8    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ ⭐  ONE THING TO DO TODAY                  Confidence 87%  │    │
│  │                                                            │    │
│  │  Contact Aisha Khanna.                                     │    │
│  │  She clicked your "Free Audit" ad twice this week and      │    │
│  │  spent 3 min on the pricing page.                          │    │
│  │                                                            │    │
│  │  Expected: 1 booked call · ₹15,000 deal value if she signs │    │
│  │                                                            │    │
│  │  [  Contact Aisha →  ]      [ See all 7 actions ]          │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                    │
│  YOUR DAY AT A GLANCE                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐                │
│  │ 3 leads     │  │ 1 post      │  │ 5 of 7        │              │
│  │ waiting     │  │ ready to    │  │ this-week     │              │
│  │ →           │  │ publish 11am│  │ actions done  │              │
│  └─────────────┘  └─────────────┘  └──────────────┘                │
│                                                                    │
│  THIS WEEK                                                         │
│  ◐ Mon  Contact 3 warm leads                            [ Do it ]  │
│  ◐ Tue  Publish reel "5 mistakes..."                    [ Open  ]  │
│  ○ Wed  Review competitor pricing change                [ See   ]  │
│  ○ Thu  Approve ₹2,400/wk ad budget shift               [ Review]  │
│                                                                    │
│  WHAT CHANGED SINCE YOU WERE LAST HERE                             │
│  ✓ Lead cost dropped to ₹104 (down ₹16 — keep current ads running) │
│  ⚠ 2 competitors started running discount ads (see Competitors)    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### What got cut from current Overview (moved to `/results`)

- Executive Summary 4-tile snapshot
- Winning Creative Formula card
- Full Performance Intelligence section
- Industry Benchmark
- Business Profile preview (→ moved to `/settings/workspace`)

### Component reuse

All existing components carry over. We're recomposing, not rewriting:

- `QuickWins` → "One thing to do today" hero
- `AiCoachPanel` → consumed by the hero
- `ActionCenter` → "This Week" strip (compressed to 4 rows)
- `ExecutiveSummary`, `WinningCreativeFormula`, `PerformanceSection`,
  `IndustryBenchmark` → moved to `/results`
- `OverviewHero` → renamed `TodayHero` with greeting + date

---

## 6. Migration plan — incremental, frontend-only

7 slices. Each ships independently and is reviewable in isolation. Zero
backend, DB, or API changes anywhere.

### Slice 1 — Sidebar + route shells + Advanced Mode toggle
- Rewrite `NAV` array: 5 groups, 8 items (per Section 3).
- Add `useAdvancedMode()` hook backed by `localStorage`.
- Conditionally append Library / Campaign Lab / Trends (raw) when Advanced
  Mode is on.
- Create 8 new route shells under `src/app/(app)/`:
  - `/today` (redirect → `/overview`)
  - `/grow/leads`, `/grow/opportunities`, `/grow/market-intelligence`
  - `/create/social-posts`, `/create/ads`, `/create/creatives`
  - `/results`
  Each is a thin redirect to the current backing page so URLs work
  immediately.
- Add legacy redirects (`/leads` → `/grow/leads`, `/content` → `/create/social-posts`,
  `/visuals` → `/create/creatives`, `/social` → `/grow/market-intelligence`,
  `/trends` → `/grow/market-intelligence`, `/performance` → `/results`,
  `/analytics` → `/results`, `/overview` → `/today`, `/ai-coach` → `/today`,
  `/bundles` → `/grow/opportunities`, `/landing-pages` → `/grow/leads`,
  `/dashboard` → `/today`).
- Update sidebar tests + add 8-item regression pin.

### Slice 2 — Settings → Preferences page
- New page at `/settings/preferences` with a single "Advanced Mode" toggle.
- Reads + writes the localStorage hook.
- Add a sub-nav entry in the settings shell.
- Tests.

### Slice 3 — Command palette refresh
- New entries for `/today`, `/grow/*`, `/create/*`, `/results`.
- Old entries marked `advanced: true` (Library, Campaign Lab, Trends, Campaigns).
- Filter advanced entries out unless `useAdvancedMode()` returns true.
- Keep old route strings in `keywords` so searching "library" / "content" /
  "visuals" still finds the right destination.
- Tests.

### Slice 4 — Today's Plan reshape
- Rebuild `/today` (was a redirect) into the real page per Section 5
  composition.
- Reuse `QuickWins`, `AiCoachPanel`, `ActionCenter` components.
- Move the dropped Overview sections (Executive Summary, Winning Creative
  Formula, Performance Intelligence, Industry Benchmark, Business Profile)
  to `/results` (slice 6).
- `/overview` keeps redirecting to `/today`.
- Tests.

### Slice 5 — Market Intelligence consolidation
- `/grow/market-intelligence` becomes a real tabbed page (Competitors |
  Trends | Audience).
- Tabs lazy-mount the existing `/social` + `/trends` page components inline.
- No new APIs — uses what `/social` and `/trends` already call.
- `/trends` raw feed becomes accessible only via direct URL / Advanced
  Mode (the `/trends` route file stays — sidebar just doesn't link to it).
- Tests.

### Slice 6 — Create section + Results page consolidation
- `/create/social-posts`, `/create/creatives` keep redirecting to `/content`
  and `/visuals` respectively (URL rename, page unchanged).
- `/results` becomes the merged Performance + Analytics page:
  hero summary + drilldown tabs (Performance Intelligence | Analytics).
- Reuses existing components from `/performance` and `/analytics`.
- Tests.

### Slice 7 — Test sweep + visual QA + report
- Full frontend test suite green (`pnpm test`, `pnpm typecheck`, `pnpm build`).
- Smoke pass: cold sign-in → primary nav · click each of 8 items.
- Advanced Mode toggle: appears, disappears items correctly.
- Regression test pinning exact 8-item primary set so a future drift
  triggers a failing test.
- Write Phase 10.3 completion report.

### What the user sees after each slice

| After slice | What changed |
|---|---|
| 1 | New sidebar visible. Every nav click works (via redirects). Bookmarks work. |
| 2 | Advanced Mode toggle live in Settings. Power users can opt-in. |
| 3 | Command palette matches new IA. Old search terms still find new pages. |
| 4 | `/today` shows the real Today's Plan (not an Overview redirect). |
| 5 | Market Intelligence is one place; competitors + trends both reachable. |
| 6 | Results is one analytics destination. Social Posts / Creatives URLs match labels. |
| 7 | Test + QA pass. Founder can demo end-to-end with confidence. |

---

## 7. Acceptance criteria (per CLAUDE.md final test)

Before shipping 10.3, every answer must be YES:

1. ✅ Would a first-time business owner understand the sidebar?
   → 7 plain-language nouns, no jargon.
2. ✅ Does Today's Plan explain business impact?
   → Hero CTA includes "Expected: 1 booked call · ₹15,000 deal value".
3. ✅ Does it recommend an action?
   → Single hero action with explicit CTA button.
4. ✅ Does it explain expected results?
   → Confidence + expected outcome on every card.
5. ✅ Does it answer "what is happening"?
   → Glance row + "what changed" section.
6. ✅ Does it answer "what should I do"?
   → One hero action, then this-week list.
7. ✅ Does it answer "what result can I expect"?
   → Every action carries a Constitution-shaped expected result.

---

## 8. Open risks

| Risk | Mitigation |
|---|---|
| Existing users have muscle memory for `/leads`, `/ads`, etc. | Legacy redirects in 10.3c. URLs keep working. |
| Bookmarks to `/library`, `/trends` break for founders not in Advanced Mode | Direct URL still resolves; we just hide it from sidebar. |
| Settings → Preferences page needs UI design | Single toggle — minimal scope. Can ship without polished page. |
| `/create/content` becomes a tabbed mega-page | Phase 10.3d ships content first, visuals/bundles incrementally. |
| Removing `/campaigns` from nav loses scheduling visibility | This-week strip on Today + scheduled-posts integration in Content. |

---

## 9. Non-goals (explicitly out of scope for 10.3)

- ❌ New features. This is a simplification pass — nothing new ships.
- ❌ Backend API redesign. Routes/services stay as-is.
- ❌ Mobile app. Web-only.
- ❌ Settings re-IA. The 7 settings subroutes from Phase 10.1 stay unchanged.
- ❌ Onboarding wizard redesign. Only the post-onboarding redirect changes.
