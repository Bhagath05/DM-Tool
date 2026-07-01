"""Marketing-strategist prompts.

Reuses the full business profile (Phase 3.1 context) plus the onboarding
analysis so the strategy is grounded, not generic. The model must justify each
pillar from the profile and never invent metrics.
"""

from __future__ import annotations

from aicmo.modules.onboarding.schemas import BusinessProfileResponse

SYSTEM_PROMPT = """You are a senior marketing strategist for a small-business owner \
with no marketing background — a cafe owner, a gym owner, a local service provider.

Produce ONE complete, multi-channel marketing strategy they can actually execute.

Discipline:
- Ground EVERY pillar in the specific business facts given (industry, products/
services, audience, stage, budget, location, USPs). The `why` for each pillar must \
reference those facts — no generic advice.
- Calibrate to the business's stage and budget. A pre-launch cafe on a tiny budget \
gets a different plan than an established SaaS. Do not over-reach.
- NEVER invent numbers — no follower counts, ad spend, revenue, or made-up metrics. \
Expected results are plain-language ranges.
- Plain English. No jargon ("CAC", "TOFU", "SOV"); if you must use a marketing idea, \
explain it in everyday words.
- Every action is concrete and verb-led ("Post a 60-second reel showing…").
- If a channel genuinely doesn't fit (e.g. influencer marketing for a tiny local \
plumber), say so honestly in `focus`/`why` and set priority "low" — never pad.

Output only what the response schema asks for."""


def build_strategy_prompt(profile: BusinessProfileResponse) -> str:
    products = ", ".join(profile.products) or "(not specified — infer from industry)"
    services = ", ".join(profile.services) or "(not specified — infer from industry)"
    usps = "; ".join(profile.unique_selling_points) or "(not specified — propose likely ones)"
    competitors = ", ".join(profile.competitors) or "(none named)"
    goals = "\n".join(f"- {g}" for g in profile.goals) or "(none provided)"
    platforms = ", ".join(profile.preferred_platforms) or "(none specified)"

    # Fold in the existing AI analysis when present, so the strategy builds on it.
    analysis_block = "(no prior analysis)"
    if profile.analysis is not None:
        a = profile.analysis
        parts = [f"Summary: {a.business_summary}"]
        if a.marketing_opportunities:
            parts.append("Opportunities: " + "; ".join(a.marketing_opportunities[:5]))
        if a.recommended_acquisition_channels:
            parts.append(
                "Prior channel picks: "
                + ", ".join(c.channel for c in a.recommended_acquisition_channels)
            )
        analysis_block = "\n".join(parts)

    return f"""Build the marketing strategy for this business.

# Business
Name: {profile.business_name}
Industry: {profile.industry}
Business type: {profile.business_type or "(not specified)"}
Products: {products}
Services: {services}
Unique selling points: {usps}
Pricing / positioning: {profile.pricing or "(not specified)"}
Growth stage: {profile.growth_stage or "(infer from the stage/resources below)"}
Location: {profile.business_location or "(not specified)"}

# Audience
{profile.target_audience}

# Stage + resources (CALIBRATE everything to these)
Current monthly leads/customers: {profile.current_monthly_leads_band or "(not specified)"}
Monthly marketing budget: {profile.monthly_budget_band or "(not specified)"}
Brand tone: {profile.brand_tone}

# Goals
Primary: {profile.primary_goal_text or "(use the list below)"}
{goals}

# Context
Preferred platforms: {platforms}
Competitors: {competitors}

# Prior AI analysis (build on this, don't contradict it)
{analysis_block}

# What to produce
A complete strategy covering: content, SEO, local SEO, paid ads, organic/social,
email, and influencer pillars (each with focus + why + concrete actions +
priority); the customer funnel (awareness → retention); a campaign roadmap; and
weekly, monthly, and quarterly plans. Then the single highest-leverage move to
start with (recommendation + reason + confidence + expected_result as a range).
"""
