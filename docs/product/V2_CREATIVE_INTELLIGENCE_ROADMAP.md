# Version 2 — AI Employee Evolution: The Creative Intelligence Layer

> **STATUS: ROADMAP ONLY. DO NOT IMPLEMENT UNTIL VERSION 1.0 HAS SHIPPED.**
> Version 1.0 stability takes priority over new intelligence. This document
> exists so the V2 vision is captured, mapped to the existing codebase, and
> ordered — not built. Implementation begins only after the V1.0 Launch
> Checklist reaches production-ready and the release is signed off.

## Thesis
The moat is the **Creative Intelligence Layer**, not any AI model. Nano Banana,
Veo 3, Seedance, GPT, Claude, Gemini and their successors are **interchangeable
execution engines** behind a stable intelligence layer. The user says *"I want
to sell this"*; the platform makes every creative decision (concept, story,
script, scene, camera, lighting, prompt) autonomously. Users never engineer
prompts, choose angles, or write scripts.

**Quality bar:** Apple / Nike / Mercedes / Rolex commercials; Netflix
cinematography; award-winning-agency copy. Not "good AI."

## The architecture already points the right way
This is **not greenfield**, and V2 must extend — never duplicate — what exists
(audit-first; see the Creative Studio Laws in `CLAUDE.md` and the design docs in
`docs/product/`). Key existing foundations:

- **Model-agnostic providers** (the exact "swappable engine" split V2 needs):
  `llm/router.py`, plus image/video/storage/**email** providers each behind a
  Protocol + registry, selected by config. **This is the core V2 requirement,
  already the architecture.**
- **Creative Studio** (`modules/creative`): brief → `design/` (layer documents +
  `apply_revision` single write path) → formats → storage → metering/cost.
  Governed by the three Creative Studio Laws (outcome-driven, no template
  categories, one design/one write path).
- **Strategy**: `modules/strategist`, `decision_engine`, `advisor` (Brand Brain
  `brain.py`, intelligence, agent reports).
- **Scene / script / prompt surface**: ~21 files touch scene/storyboard/shot,
  ~15 script/dialogue, ~19 prompt-compilation — already internal, never exposed.
- **Quality + performance + learning**: ~8 files score/judge/rank, ~7
  predict/ctr/roas, `modules/learning` (`CampaignExperiment`, `ExperimentResult`,
  `LearningEvent`), `modules/performance`, and the autonomous `operations` loop.
- **Brand Brain** (`business_profiles` + `context/builder.render_context_block`)
  already inherits into every generation — the Brand Intelligence Engine's core.

## The 17 engines — mapped to reality (status is honest, from a code audit)

| # | Engine | Status | Existing anchor | V2 work |
|---|---|---|---|---|
| 1 | Brand Intelligence | ✅ strong | Brand Brain + `context/builder` + `advisor/brain` | history/campaign memory depth |
| 2 | Market Intelligence | ⚠️ partial | `competitors`, `trends`, market-intelligence page | continuous external ad/pricing research feeds |
| 3 | Audience Pulse | ⚠️ thin | onboarding `analysis` audience insights | psychology/culture/memes/social-listening depth — **major** |
| 4 | Consumer Psychology | ❌ new | persuasion cues in prompts only | dedicated framework engine (scarcity/authority/FOMO/biases) |
| 5 | Trend Intelligence | ⚠️ partial | `trends` module | per-platform viral/hook/transition/music tracking |
| 6 | Creative Strategy | ⚠️ partial | `strategist` + creative brief | 10 **distinct concepts** (luxury/UGC/founder/…), not variations |
| 7 | Story Intelligence | ⚠️ partial | scene/script files | emotional-arc-first (attention→…→action) before any script |
| 8 | Script Intelligence | ⚠️ partial | ~15 script/dialogue files | agency-grade scripts w/ purpose+psychology+objective per line |
| 9 | Scene Intelligence | ⚠️ partial | ~21 scene/shot files | full unambiguous scene spec (wardrobe/lens/DoF/…) |
| 10 | Prompt Compiler | ✅ present | ~19 prompt-compile files; prompts never exposed (Law) | per-model optimized compilation, provider-matrixed |
| 11 | Character Consistency | ⚠️ partial | ~4 persona/consistency files | reusable Character Profile store + reference across scenes — **new store** |
| 12 | Product Consistency | ❌ new | Brand Brain has logo/colours | Product Identity store (materials/labels/reflections/dims) — **new store** |
| 13 | Image Quality Judge | ⚠️ partial | ~8 score/judge files | multi-axis score + auto-regenerate-below-threshold loop |
| 14 | Video Quality Judge | ⚠️ partial | quality files + `video` | lip-sync/continuity/physics scoring + regenerate |
| 15 | Performance Prediction | ⚠️ partial | `performance`, `advisor`, ~7 predict files | pre-flight CTR/watch/ROAS/scroll-stop prediction |
| 16 | Experimentation | ⚠️ partial | `learning` experiments + ~16 hook/variant files | campaign→hook→CTA→open→end fan-out (hundreds), ranked |
| 17 | Autonomous Optimization | ⚠️ partial | `operations` loop + `learning.synthesis` + `autonomy` policy | live-signal ingestion → auto-smarter future campaigns |

**Legend:** ✅ largely exists · ⚠️ partial, needs deepening · ❌ genuinely new.
Net: **~2 net-new engines (4, 12), ~2 new persistent stores (11, 12), and the
rest is deepening existing modules to the agency-quality bar** — plus wiring
them into one autonomous pipeline. It is large, but it is evolution, not a
rebuild.

## Non-negotiable V2 design rules
1. **Intelligence layer ⟂ execution engines.** No engine may hardcode a model.
   Every model call goes through a provider Protocol + the LLM/image/video
   router. Swapping Nano Banana → a successor must not touch any engine.
2. **Prompts never surface.** Compilation stays internal (existing invariant).
3. **Reuse before build.** Each engine's V2 ticket starts with an audit of its
   existing anchor module; extend it, never fork it. Respect the three Creative
   Studio Laws and the Editability Invariant.
4. **Every asset traceable to the Growth Objective** it serves (Law 1) and
   judged on that objective's KPI.
5. **Human approval preserved.** Autonomy proposes; nothing publishes without
   the approval flow (V1.0 autonomy policy + work queue).

## Suggested implementation order (post-V1.0; each ships independently)
1. **Consistency stores first** (11 Character, 12 Product) — everything visual
   depends on them.
2. **Quality Judges + regenerate loop** (13, 14) — quality gate before scale.
3. **Creative Strategy → Story → Script → Scene deepening** (6→7→8→9) — the
   concept-to-storyboard spine, on top of the existing creative brief.
4. **Prompt Compiler matrix** (10) — per-model optimization once scenes are rich.
5. **Experimentation fan-out + Performance Prediction** (16, 15) — generate many,
   predict, rank, promote only winners.
6. **Deep Audience Pulse + Consumer Psychology + Market/Trend feeds** (3, 4, 2,
   5) — the research engines that feed strategy; heaviest external-data lift.
7. **Autonomous Optimization** (17) — closes the loop into the `operations`
   pipeline.

## Explicit gate
Nothing in this document is implemented until:
- V1.0 Launch Checklist is production-ready (Waves 0–3 complete + verified), and
- the release owner signs off on starting V2.

Until then: **V1.0 stability over new intelligence.**
