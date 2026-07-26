# North Star — The Autonomous Growth Operating System

> **STATUS: VISION / DOCUMENTATION ONLY. DO NOT IMPLEMENT UNTIL V1.0 SHIPS.**
> This is the umbrella product vision over the V2 roadmap. It records intent
> and maps it to the existing codebase so V2 extends rather than rebuilds.
> Feature freeze holds; V1.0 production-readiness is the current priority.

## The vision in one line
Businesses shouldn't have to become marketers. DM Tool is their **AI Growth
Team** — an AI Digital Twin of the business that thinks, reasons, plans,
creates, executes, measures, learns, and improves autonomously. The user hires
one AI, not twenty SaaS tools.

## The North Star test (apply to every future feature)
1. Does this make the AI **think better**?
2. Does this make businesses **grow faster**?
3. Does this **remove work** from the customer?

If not all-yes → don't build it. Underlying question: *"Will this help the
business make more money with less effort?"*

## The moat (not the models)
GPT / Claude / Gemini / Nano Banana / Veo / Seedance are interchangeable
execution engines. The moat is: Business Intelligence · Creative Intelligence ·
Audience Intelligence · Decision Intelligence · Autonomous Learning · the
**Digital Twin** · Business Memory · Reasoning · Execution. Enforced
architecturally by the provider-Protocol + router split (already in place).

## The Digital Twin is already skeletoned — V2 deepens it
The "AI Business Brain / Digital Twin" is not greenfield:

| Twin capability | Existing anchor |
|---|---|
| Business understanding (products/audience/brand/voice/rules/competitors) | **Brand Brain** — `business_profiles` + `context/builder.render_context_block` (inherited into every generation) |
| Continuous reasoning + advice ("advise, don't just report") | `advisor` (`brain`, `intelligence`, `agent`, **`health`**), `decision_engine` |
| Works while the owner sleeps (daily read → improve → notify) | `operations` autonomous loop + `autonomy` policy + `orchestrator` + `planner` |
| Self-improving memory (winning hooks/CTAs/etc.) | `learning` (`CampaignExperiment`, `ExperimentResult`, `LearningEvent`) |
| AI CRM (auto contacts/leads/deals/tasks) | `crm` module (entities/tasks/email/dashboard) |
| Unified business memory across channels | `integrations` platform (see `V2_INTEGRATIONS_PLATFORM.md`) |
| Predictive (CTR/ROAS/CPA/churn before launch) | `performance` + advisor prediction (deepen for pre-flight) |
| Business Health Scores (few scores, not charts) | **`advisor/health.py`** (Brand/Content/Website/Ads/Leads/Social/Growth — shipped in V1) |
| Creative Intelligence (research→script→scene→prompt→gen) | `V2_CREATIVE_INTELLIGENCE_ROADMAP.md` (17 engines) |

**Implication:** V2 is the *deepening + connecting* of these into one Digital
Twin with a shared business memory and an autonomous goal-seeking loop — not a
new product build.

## The long-term goal (the acceptance test for "done")
The owner says *"increase revenue 30% this quarter"* and the AI determines the
campaigns, ads, content, audiences, channels, offers, and budget — and
continuously optimizes toward the goal. This is the `operations` +
`decision_engine` + `autonomy` loop, fed by the Digital Twin and the
integrations data, closing on a revenue objective. It is **V2 Priority #4
(Autonomous Campaign Engine)**.

## How this maps onto the locked V2 order
1. **Integrations Platform** — the unified business memory (every channel →
   one normalized schema the Twin reads). `V2_INTEGRATIONS_PLATFORM.md`
2. **Creative Intelligence Engine** — the autonomous creative brain.
   `V2_CREATIVE_INTELLIGENCE_ROADMAP.md`
3. **AI Ad Studio** — many campaigns × hooks × styles × CTAs, ranked; promote
   only winners (predictive gate).
4. **Autonomous Campaign Engine** — goal-in → autonomous execution/optimization
   out; the "works while you sleep" loop closing on business goals.

The Digital Twin + Business Memory + North Star test are the connective tissue
across all four.

## Zero-setup principle (design constraint for V2)
Assume the business has only Instagram / WhatsApp / email / website / phone. The
AI creates everything else (CRM, analytics, content, campaigns). Never ask users
to configure pipelines or write prompts. This constraint applies to every V2
surface.

## Gate
Nothing here is implemented until V1.0 is production-ready and verified. Then V2
proceeds in the locked order, evaluated against the North Star test, with the
Digital Twin as the organizing architecture.
