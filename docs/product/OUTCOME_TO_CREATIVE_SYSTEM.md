# DM Tool — The Outcome-to-Creative System (canonical contract)

> The authoritative spec that ties the Growth Platform to the Creative
> Studio. Governs CS1+ implementation. Synthesizes + supersedes the
> positioning across `OUTCOME_DRIVEN_ALIGNMENT.md` and
> `CREATIVE_STUDIO_ARCHITECTURE.md`. Architecture only — no code.
> Date: 2026-06-11.

## The three laws

1. **The user asks for outcomes.** ("Generate leads", "get bookings",
   "hire engineers", "drive app installs.")
2. **The platform decides the creative strategy.** (Strategy Engine —
   channels, messaging, formats, what creative is even needed.)
3. **The Creative Studio produces and edits the assets.** (Layer-based,
   editable, multi-format.)

DM Tool is an **Outcome-to-Creative system**, not a template generator and
not a design tool with a marketing skin. The creative is a *consequence*
of a business goal, never the starting point.

---

## 1. The canonical pipeline (who owns each step)

```
[1] OUTCOME INTAKE          user states a goal (NL)            → growth_objective
       Generate leads · Bookings · Sales · Promote event · Hire ·
       Launch product · Brand awareness · App installs · Grow social
          │  (+ optional inputs §2)
          ▼
[2] CONTEXT RESOLUTION      business_profile + market intel    → audience, positioning
          ▼
[3] STRATEGY ENGINE         LLM planner                        → campaign_plans:
       • campaign strategy   • messaging framework   • content plan
       • channel selection   • CREATIVE REQUIREMENTS (the asset plan)
          ▼  asset plan = [(creative_type, format, brief, variant_spec), …]
          ▼
[4] CREATIVE STUDIO         composers per requirement          → creative_design (editable!)
       posters · social posts · carousels · ad creatives · thumbnails ·
       landing-page creatives · reels · videos
          │  render
          ▼
       creative_asset (a render of the design)  +  creative_variant (A/B)
          ▼
[5] EDIT / TRANSFORM        user or AI refines                 → new design revisions
          ▼
[6] DISTRIBUTE → MEASURE → OPTIMIZE   (roadmap Phase C; judged on the objective KPI)
```

**Module ownership:** [1][2] `modules/growth` (the Strategy Engine, new) +
existing onboarding/market-intel; [3] Strategy Engine; [4][5] Creative
Studio (`modules/creative` core + `modules/video` subsystem); [6]
integrations + analytics + Learning Lab (existing/roadmap).

The user **never picks an asset type in Simple Mode** — the Strategy
Engine's asset plan decides what gets made. "I need more bookings" might
produce a carousel + a reel + 3 ad variants + a landing-page hero, and the
founder simply reviews outcomes.

---

## 2. Inputs contract

| Input | Required? | Flows into |
|---|---|---|
| **Business goal / outcome** | ✅ required | `growth_objective.objective_kind` + statement |
| Website | optional | scrape → positioning/brand-color seed/voice |
| Brand assets (logo/fonts/colors) | optional | `brand_kit` + `brand_asset`; brand tokens |
| Product / service details | optional | `business_profile`; offer in briefs |
| Audience | optional (else AI-derived) | `growth_objective.audience_hypothesis` |
| Budget | optional | strategy channel/format split |
| Campaign objective (tactic) | optional | `campaign_plans` strategy choices |

Only the goal is mandatory; everything the founder omits, the platform
infers (and shows, editably, per the Constitution's recommendation
contract — reason + confidence + expected result).

---

## 3. Two hard invariants (architecturally enforced)

### 3.1 Editability Invariant (already specified — §0.1 of the Studio doc)
Every creative is a `creative_design` (editable layers) first; the
rendered file is an output cache. No path from brief → `creative_asset`
bypasses a design.

### 3.2 No-Template-Categories Invariant (NEW — first-class rule)

> **The system MUST NOT contain predefined template categories** —
> no "restaurant templates", "healthcare templates", "hiring templates",
> no industry-tagged template tables, no industry enum, no `if industry ==
> …` branch anywhere in composition. Templates are **generated
> dynamically** from: design primitives + layout systems + brand tokens +
> objective-specific composition rules — parameterized by **(objective,
> audience, brand, platform, strategy)**. Industry is *free-text context
> that flows into prompts*, never a code dimension.

Enforcement (structural, reviewable):
- `creative_template` rows are **generated or user-saved outputs** (a cache
  of good designs), tenant-owned — never a curated, industry-tagged
  catalog. There is no `industry` column on templates, formats, or the
  objective taxonomy.
- The composer's layout choice comes from a **`layout_primitive` library**
  (grids, hierarchy patterns, focal compositions, type scales,
  color-system *generators*) selected + parameterized by the LLM from the
  objective + audience + platform + brand — not from a per-industry asset
  set.
- A CI/review guard: a grep for industry literals in `modules/creative`,
  `modules/growth`, and prompt files must find them **only inside
  prompt-context strings**, never in control flow or table seeds. (Already
  true today — verified zero industry hardcoding — and made a permanent
  rule.)

This is what makes the studio serve recruitment, healthcare, insurance,
education, restaurants, real estate, SaaS, cybersecurity, e-commerce,
consulting, events, hospitality, manufacturing, automotive, finance, and
retail with **one** code path: the *outcome* shape (leads/bookings/…) is
universal; the *industry* is just words in the prompt.

---

## 4. The dynamic template engine (replaces "template categories")

```
objective (e.g. bookings) + audience + brand_kit + platform/format + strategy
   │
   ├─ layout system   ← layout_primitive library, chosen by composition rules
   │                     ("strong-offer layout" for sales, "credibility
   │                      layout" for B2B leads, "social-proof" for events…)
   ├─ color system    ← generated from brand tokens + objective mood
   │                     (urgency vs premium vs trust) — not a fixed palette
   ├─ type system     ← brand fonts + scale rules for the format
   ├─ copy            ← content engine, objective-framed (hook→value→CTA)
   ├─ imagery         ← image/video provider, prompt = objective+audience+brand
   └─ brand layers    ← logo, end-card, safe zones from brand_kit
   ▼
creative_design  (one editable, on-brand result — saved as a template if liked)
```

Objective-specific **composition rules** (code-defined, industry-free) are
the studio's taste: e.g. a *lead-gen* design foregrounds a single CTA +
value prop + trust signal; an *event* design foregrounds date/time/place +
urgency; a *hiring* design foregrounds role + culture + apply CTA. These
rules reference *outcome semantics*, never industries.

---

## 5. The full editing contract (every action → mechanism)

| Action | Mechanism | New? |
|---|---|---|
| Edit text | direct edit / AI edit | — |
| Replace images | swap source (library/upload/regenerate) | — |
| **Replace logos** | swap `role:logo` layer's `brand_asset` ref | covered |
| Change colors | edit prop / re-point brand token / AI edit | — |
| **Change fonts** | edit `font_family` (incl. `brand:*` token) | covered |
| Move layers | `move_layer` | — |
| **Resize elements** | `update_layer` geometry (w/h/scale) | covered |
| Regenerate individual sections | targeted regenerate (§5.1) | — |
| Generate variations | fork → vary one variable → `creative_variant` | — |
| **Generate platform-specific versions** | **Creative Transform §6** (re-target format/platform) | **NEW** |
| Brand swap | swap active `brand_kit` → tokens re-resolve | — |
| AI-assisted NL editing | NL → validated EditOps | — |
| **Style variants ("luxury", "modern")** | **Style-Variant generation §6** | **NEW** |
| **Media transforms (poster→carousel→reel)** | **Creative Transform §6** | **NEW** |

---

## 6. Two new capabilities (added to the Studio architecture)

### 6.1 Creative Transforms — `POST /creative/designs/{id}/transform`
Distinct from *export* (which renders the SAME design to a format).
A transform produces a **new `creative_design`** that may change page
count or media type:

| Example instruction | Transform kind | What happens |
|---|---|---|
| "Convert to Instagram Story" / "Make for LinkedIn" | `reformat` | re-target `creative_format`; auto-layout resize + platform-appropriate copy re-voice |
| "Turn this poster into a carousel" | `recompose` | LLM decomposes the single message into an N-slide narrative → N design pages |
| "Turn this carousel into a reel" | `remediate` | pages → video scenes; add transitions/animation + optional Veo motion + TTS VO → `media_type=video` |
| "Turn this reel into a poster" | `remediate` | pick the key frame/message → single static page |

Transforms reuse the composers + Strategy context, are metered
(`generation`/`video_generation`) + cost-tracked + audited, and the source
design is preserved (transform = derive, never mutate).

### 6.2 Style-Variant generation — `POST /creative/designs/{id}/restyle`
"Create a luxury version", "Create a modern version", "make it playful".
Keeps **message + objective + layout intent**, re-derives the **visual
system** (color/type/imagery direction) from a style descriptor through the
dynamic template engine (§4). Distinct from brand-swap (applies the
existing kit) and A/B variant (changes one variable). Produces a new
design (or a fork set: "create 5 variants" → 5 restyles/forks in one
fan-out job).

Both land on existing tables (`creative_design` + `creative_variant`) — no
schema change beyond CS1.

---

## 7. NL example → mechanism (the requested examples, all buildable)

| "…" | Resolves to |
|---|---|
| "Make the CTA stronger" | AI edit → EditOps on `role:cta` text (copy engine) |
| "Change colors to match my brand" | re-point brand tokens → re-resolve at render |
| "Replace the person in the image" | section regenerate `role:product`/image layer (image provider, inpaint/replace) |
| "Create a luxury version" | restyle (§6.2) |
| "Create a modern version" | restyle (§6.2) |
| "Make this suitable for LinkedIn" | transform `reformat` (§6.1) |
| "Convert this into Instagram Story format" | transform `reformat` → 9:16 |
| "Turn this poster into a carousel" | transform `recompose` (§6.1) |
| "Turn this carousel into a reel" | transform `remediate` → video |
| "Create 5 variants" | variant fan-out (fork + per-variable change), one Arq job |

A single NL router classifies the instruction into {edit · regenerate ·
transform · restyle · variant} and dispatches — all returning new design
revisions, all undoable, all metered + audited.

---

## 8. Industry-agnostic guarantee (restated as a test)

For any of the 16+ industries, the *only* difference in the system is the
text in `business_profile.industry`, `growth_objective.statement`, and the
audience — which flow into prompts. **Acceptance test:** swapping the
industry string changes the generated copy/imagery, but exercises the
**same** composers, layout primitives, formats, objective taxonomy, and
code paths. If any feature needs a new code branch or template seed to
support a new industry, that is a bug against this contract.

---

## 9. Build alignment (no new phases — folds into CS1+)

- **CS1 (amended already):** design model + `growth_objective` +
  `objective_kind` catalog. **Add:** `layout_primitive` registry stub +
  the no-industry-hardcoding review guard.
- **CS3:** Strategy Engine + composers built on the dynamic template
  engine (§4) — never a category catalog.
- **CS4:** AI editing + the NL router that also dispatches transforms +
  restyles (§6–7).
- **CS6:** transform/restyle UX polish; "save as template" (generated
  cache).

Everything else (Phases 2–6 of the main roadmap) is unchanged and now
clearly framed: the Autopilot is the Strategy Engine on a schedule; the
closed loop optimizes the objective KPI by reshaping the next asset plan.

---

## 10. Proposed CLAUDE.md addendum (one paragraph)

> **OUTCOME-TO-CREATIVE RULE.** DM Tool's primary object is the business
> outcome (the Growth Objective). The user asks for outcomes; the Strategy
> Engine decides the creative strategy; the Creative Studio produces +
> edits assets. Asset types are implementation details Simple Mode never
> surfaces. Every creative is an editable layer document; the file is a
> render. There are **no predefined template categories and no
> industry-specific code branches** — industry is free-text prompt context
> only; templates are generated from design primitives + brand tokens +
> objective composition rules. Every artifact is traceable (by FK) to the
> objective it serves and judged on that objective's KPI.
