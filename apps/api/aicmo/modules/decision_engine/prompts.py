"""Decision Engine prompts — real signals in, structured decisions out."""

from __future__ import annotations

from aicmo.modules.decision_engine.schemas import DecisionSignals

SYSTEM_PROMPT = """You are the decision-making layer for a small business's marketing.

You are given a SNAPSHOT of real data from the workspace. Reason over it and
output structured DECISIONS — never actions, and never anything to run automatically.

Iron rules:
- Ground EVERY decision in the numbers/facts in the snapshot. Quote them in
  `evidence`. If a fact isn't in the snapshot, you do not know it — do NOT invent
  followers, spend, revenue, CTR, or any metric that wasn't given.
- If the data is too thin to decide responsibly, produce FEWER decisions and be
  explicit about the gap (in `data_sufficiency` and each decision's `evidence`).
  "Not enough data yet — here's what to collect first" is a valid, honest decision.
- Expected impact is a plain-language range, never a single fabricated number.
- Calibrate confidence to the strength of the evidence: strong recent data → high;
  a single data point or none → low, and say why.
- You advise; a human executes. Recommend, never assume anything was published,
  scheduled, or spent.
- Plain English, no jargon.

Output only what the response schema asks for."""


def build_decision_prompt(s: DecisionSignals) -> str:
    if not s.has_profile:
        profile_block = (
            "No business profile yet — there is almost no context to decide on. "
            "The main decision is to complete onboarding."
        )
    else:
        goal = s.primary_goal or (", ".join(s.goals) or "not stated")
        profile_block = (
            f"Business: {s.business_name} ({s.industry}); stage: "
            f"{s.growth_stage or 'unknown'}\n"
            f"Primary goal: {goal}\n"
            f"Competitors tracked: {', '.join(s.competitors) or 'none'}"
        )

    conv = round(s.conversion_rate * 100, 1)
    strat = f" — top move: {s.strategy_top_move}" if s.strategy_top_move else ""

    memory_parts = []
    if s.winning_patterns:
        memory_parts.append(
            "What has won before:\n" + "\n".join(f"- {w}" for w in s.winning_patterns)
        )
    if s.audience_patterns:
        memory_parts.append(
            "Audience patterns:\n" + "\n".join(f"- {a}" for a in s.audience_patterns)
        )
    memory_block = "\n".join(memory_parts) or (
        "(no learned patterns yet — not enough published history to learn from)"
    )

    return f"""Decide what this business should do next, based ONLY on the real data below.

# Business
{profile_block}

# Leads & site (real analytics)
Total leads: {s.total_leads} | last 7d: {s.leads_7d} | last 30d: {s.leads_30d} | hot: {s.hot_leads}
Landing pages published: {s.landing_pages_published} | total views: {s.total_views} | conversion: {conv}%

# Paid / creative performance
Has performance data: {s.performance_has_data} | rows: {s.performance_rows} | creatives tracked: {s.creatives_tracked} | diagnostics: {s.performance_diagnostics}

# Publishing
Scheduled: {s.scheduled_posts} | published: {s.published_posts} | failed: {s.failed_posts}

# Strategy
Has a marketing strategy: {s.has_strategy}{strat}

# Learned memory (what actually worked in past posts — prefer these over guesses)
{memory_block}

# What to produce
Prioritised, structured decisions grounded ONLY in the numbers above — each with
decision, reasoning, exact evidence (quote the numbers), expected impact (range),
confidence, urgency, recommended action, alternatives, risks, the business
objective it serves, and affected channels. Then an honest `data_sufficiency`
note. Fewer well-evidenced decisions beat many weak ones.
"""
