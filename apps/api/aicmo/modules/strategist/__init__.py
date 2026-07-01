"""Phase 3.2 — Marketing Strategist.

Turns the business profile (Phase 3.1 context) + the onboarding analysis into
ONE comprehensive, multi-channel marketing strategy: content, SEO, local SEO,
paid ads, organic/social, email, influencer, a customer funnel, a campaign
roadmap, and weekly/monthly/quarterly plans.

Reuses the existing LLM router + business profile; persists to its own
per-brand, versioned table so the Planner (3.3) and Campaign Execution (3.4)
can consume the latest strategy. Structured output only — every pillar
explains WHY and is grounded in the real profile; nothing fabricated.
"""
