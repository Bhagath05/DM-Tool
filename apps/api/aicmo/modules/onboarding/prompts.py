"""Prompts for the Intelligence Engine.

Phase 2.1 — the analyser now produces a consultant deliverable, not a
chatbot paragraph. The system prompt frames the model as a senior
strategist; the user prompt grounds the analysis in the new conversational
profile fields (location, leads band, budget band, primary-goal text).
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.modules.onboarding.schemas import BusinessProfileBase

SYSTEM_PROMPT = (
    """You are a senior business growth strategist + performance \
marketer. You are NOT a chatbot. You are producing a tight CONSULTANT \
DELIVERABLE that a busy founder will skim in 90 seconds and execute on.

Discipline:
- Ground every claim in the profile context. Never invent statistics, \
customer counts, competitor names, or benchmarks.
- Calibrate to the founder's STAGE (current monthly leads band) and \
RESOURCES (monthly budget band). Recommendations for a "Just starting / \
Nothing yet" business look very different from a "$5k+ / 500-5000" business.
- Be honest. If the user's primary goal looks ambitious for their current \
stage/budget, set realistic_growth_path milestones that get them there \
incrementally — don't promise overnight outcomes.
- Every "gap", "bottleneck", and "channel" must be SPECIFIC to this \
business. "Improve SEO" is not specific. "Rewrite the home page H1 to \
promise a payoff" is specific.

Output only what the response schema asks for. No preamble, no apology, \
no hedging. The schema has BOTH legacy fields and v2 strategist fields — \
fill EVERY field, including the v2 fields (current_state, \
desired_future_state, gap_analysis, growth_bottlenecks, \
competitor_signals, realistic_growth_path, \
recommended_acquisition_channels).

"""
    + TONE_GUARDRAILS
)


def build_analysis_user_prompt(profile: BusinessProfileBase) -> str:
    competitors = ", ".join(profile.competitors) or "(none provided — infer plausible categories, do not name fake brands)"
    goals = "\n".join(f"- {g}" for g in profile.goals) or "(none provided)"
    platforms = ", ".join(profile.preferred_platforms)

    # Phase 2.0 / 2.1 fields. All optional — fall back gracefully.
    location = profile.business_location or "(not specified — assume the user's audience is wherever they are based)"
    leads_band = profile.current_monthly_leads_band or "(not specified)"
    budget_band = profile.monthly_budget_band or "(not specified)"
    primary_goal = profile.primary_goal_text or "(use the goals list above)"

    # Phase 3.1 — business-understanding context. Absent fields tell the model
    # to infer plausibly (never fabricate specifics like fake product names).
    products = ", ".join(profile.products) or "(not specified — infer from industry + name)"
    services = ", ".join(profile.services) or "(not specified — infer from industry + name)"
    usps = "; ".join(profile.unique_selling_points) or "(not specified — propose likely differentiators)"
    pricing = profile.pricing or "(not specified)"
    growth_stage = profile.growth_stage or "(infer from the traction band below)"

    return f"""Produce a strategist analysis for this business.

# Business
Name: {profile.business_name}
Industry: {profile.industry}
Business type: {profile.business_type or "(not specified)"}
Products: {products}
Services: {services}
Unique selling points: {usps}
Pricing / positioning: {pricing}
Website: {profile.website or "(none)"}
Location: {location}

# Audience
{profile.target_audience}

# Stage + Resources (use to CALIBRATE every recommendation)
Growth stage: {growth_stage}
Current monthly leads/customers: {leads_band}
Monthly marketing budget: {budget_band}
Brand tone: {profile.brand_tone}

# What the founder wants
Primary goal: {primary_goal}
Other goals:
{goals}

# Context
Preferred platforms: {platforms}
Known competitors: {competitors}

# What to produce

Fill EVERY field in the schema. Critical guidance per field:

- `business_summary`: 2-3 sentences. What this business IS and who it's for. \
Sharp positioning, not a tagline.

- `audience_insights`: 3-5 insights. Behaviours and motivations, not "Gen-Z \
women aged 22-30". Each insight should make the founder go "huh, true".

- `marketing_opportunities`: 3-5 specific opportunities. "Run Facebook ads" \
is not an opportunity. "Build a free pre-launch waitlist with a 24h flash \
discount unlocker" is an opportunity.

- `content_directions`: 3-5 angles. Each maps to ONE of: {platforms}. Don't \
recommend platforms not in that list.

- `strategy_recommendation`: One paragraph. Sequence the next 30-60 days as \
a concrete order of operations — what to do week 1, week 2, etc.

- `current_state`: Honest snapshot. Reference the leads_band and budget_band. \
If the brand is still pre-traction, say so. Don't flatter.

- `desired_future_state`: Restate the founder's primary goal as a concrete \
end-state — what the business looks like the day they hit it.

- `gap_analysis`: Name the 2-3 BIGGEST gaps. Not 8 gaps — 2-3. Be ruthless.

- `growth_bottlenecks`: 3-5 specific blockers. Examples that pass the bar: \
"No way to capture leads from Instagram traffic", "Brand voice is generic — \
indistinguishable from 5 competitors". Examples that FAIL: "Lack of \
engagement", "Inconsistent posting".

- `competitor_signals`: 3-5 plausible moves competitors in this industry \
are making that this business should watch or counter. NO fabricated brand \
names. Use categories ("Mid-tier specialty-coffee chains in this region") \
or descriptions ("Indie creators in this niche running pre-launch waitlists").

- `realistic_growth_path`: 3 phases. Each phase has a time-horizon, ONE \
primary goal (do NOT list five), 2-4 actions, and ONE success_metric NAME \
to watch (the metric NAME — never invent a target number). Calibrate the \
ambition to budget_band and leads_band. If they're starting from zero with \
no budget, Phase 1 cannot be "100k followers". It's "first 10 customers".

- `recommended_acquisition_channels`: Top 3 channels for THIS stage. Rank \
them. For each: why_now ties to budget/stage, expected_outcome is a plain- \
English realistic outcome over 30-60 days.

Remember: a real strategist sounds calm, specific, and honest. Not \
optimistic, not pessimistic — accurate.
"""
