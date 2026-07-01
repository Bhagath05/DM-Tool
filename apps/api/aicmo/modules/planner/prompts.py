"""Planner prompts — strategy + profile → today's concrete tasks."""

from __future__ import annotations

from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.strategist.schemas import MarketingStrategy

SYSTEM_PROMPT = """You are the daily planner for a small-business owner's marketing.

Turn their marketing strategy into TODAY's concrete to-do list — a short,
realistic set of tasks a busy founder can actually finish today.

Discipline:
- 3-7 tasks, no more. A founder cannot do 12 things. Prioritise ruthlessly.
- Each task is a concrete, imperative action grounded in the strategy or a real
  signal. The `why` must reference the strategy/profile — no generic filler.
- NEVER invent numbers (followers, spend, revenue). No fake metrics.
- Plain English. No jargon.
- You are PLANNING, not doing. Name where the human would act in
  `suggested_action`, but never assume anything is published, sent, or spent.
- Mix effort levels so the day is doable — not seven deep tasks.

Output only what the response schema asks for."""


def build_plan_prompt(
    profile: BusinessProfileResponse, strategy: MarketingStrategy | None
) -> str:
    goals = "; ".join(profile.goals) or "(none provided)"

    if strategy is not None:
        pillars = [
            ("Content", strategy.content),
            ("SEO", strategy.seo),
            ("Local SEO", strategy.local_seo),
            ("Paid ads", strategy.paid_ads),
            ("Organic/social", strategy.organic_social),
            ("Email", strategy.email),
            ("Influencer", strategy.influencer),
        ]
        pillar_lines = "\n".join(
            f"- {name} ({p.priority}): {p.focus}" for name, p in pillars
        )
        strategy_block = f"""Positioning: {strategy.positioning}
This week's focus: {strategy.weekly_plan.focus}
This week's milestones:
{chr(10).join(f"- {m}" for m in strategy.weekly_plan.milestones)}
Campaign roadmap: {"; ".join(strategy.campaign_roadmap)}
Channel priorities:
{pillar_lines}
Strategy's top move: {strategy.recommendation}"""
    else:
        strategy_block = "(no marketing strategy yet — plan sensibly from the business below, and include one task to generate a strategy)"

    return f"""Plan today's marketing tasks for this business.

# Business
Name: {profile.business_name}
Industry: {profile.industry}
Growth stage: {profile.growth_stage or "(not specified)"}
Preferred platforms: {", ".join(profile.preferred_platforms) or "(none)"}
Primary goal: {profile.primary_goal_text or goals}
Monthly budget: {profile.monthly_budget_band or "(not specified)"}

# Marketing strategy (ground today's plan in THIS)
{strategy_block}

# What to produce
Today's plan: a summary line, the single focus, and 3-7 prioritized tasks that
move this week's milestones forward. Each task: title, category, why (tied to
the strategy), priority, effort, and where the human would do it.
"""
