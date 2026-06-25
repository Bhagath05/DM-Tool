from __future__ import annotations

from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import RawTrends

SYSTEM_PROMPT = """You are an AI marketing advisor for a small-business owner who \
has zero marketing background. They are a restaurant owner, a gym owner, a real \
estate agent, or a local shop owner — never a marketer.

Given a business profile and fresh trend signals from Google Trends and Reddit, \
produce a tightly-focused report the founder can act on this week. Every trend \
must read like advice from a consultant: name what's happening, tell the founder \
exactly what to do, predict the outcome, and explain why.

Output discipline:
- Be specific, never generic. Tie every claim to a real trend signal or to \
the founder's audience.
- Plain English only. No marketing jargon ("CTR", "ICP", "funnel", "TOFU/BOFU", \
"engagement rate"). If you must reference a metric, spell it out in normal words.
- Imperative voice for actions ("Post a 60-second reel about…"). No hedging.
- Calibrate confidence honestly. Reserve 80+ for trends with strong, recent \
signals AND a clean fit with the business. Use 40-60 for weak fit or thin data.
- Output only what the response schema asks for."""


def build_user_prompt(profile: BusinessProfileResponse, raw: RawTrends) -> str:
    competitors = ", ".join(profile.competitors) or "(none provided)"
    goals = "\n".join(f"- {g}" for g in profile.goals)
    platforms = ", ".join(profile.preferred_platforms)

    google_block = _format_google_block(raw)
    reddit_block = _format_reddit_block(raw)

    return f"""# Business
- Name: {profile.business_name}
- Industry: {profile.industry}
- Brand tone: {profile.brand_tone}
- Preferred platforms: {platforms}
- Competitors: {competitors}

Audience:
{profile.target_audience}

Goals:
{goals}

# Fresh trend signals

## Google Trends (related + rising queries)
{google_block or "(no data — Google Trends fetch failed)"}

## Reddit (hot posts matching the niche)
{reddit_block or "(no data — Reddit fetch failed)"}

# Requirements
- Trending topics must reference signals above, not generic seasonality.
- Aim for 3-6 trending topics when signal allows; fewer is acceptable when
  data is sparse (e.g. one source unavailable), but never zero.
- For EVERY trending topic, populate ALL of these fields (none optional):
    • topic — short noun-phrase (e.g. "specialty coffee guides")
    • why_it_matters — one sentence the founder can read as "what is
      happening for my business right now"
    • recommended_action — the single concrete thing to do this week.
      Imperative, no jargon. e.g. "Post a 60-second Instagram reel
      walking through your espresso bean selection."
    • expected_result — plain-language outcome over the next 7-14 days.
      Always include a range, never a single magic number.
      e.g. "Likely 80-150 extra people see it; 1-3 walk in this week."
    • confidence — integer 1-100. Reserve 80+ for trends with strong,
      recent signals AND a clean business fit. Use 40-60 for weak fit
      or thin data. Different topics MUST get different scores.
    • reason — one sentence citing the specific signal or fit driving
      that confidence. e.g. "'Espresso bean comparison' rising +45% on
      Google Trends, and your audience is already on Instagram."
    • suggested_angles — 1-4 distinct content angles
- Aim for 3-5 content ideas. Each content idea MUST include ALL of these
  fields (none are optional):
    • platform — one of: {platforms}
    • format   — concrete format keyword (reel, carousel, short, tweet,
                 thread, story, email, blog, podcast — pick the closest)
    • hook     — the literal first line / first second of the piece
    • description — 2-3 sentences on what the piece covers
- Hashtags must be relevant to the chosen theme and platform conventions
  (at least 3 per cluster, no fewer).
"""


def _format_google_block(raw: RawTrends) -> str:
    if not raw.google_trends:
        return ""
    lines: list[str] = []
    for item in raw.google_trends:
        lines.append(f"- {item.keyword}")
        if item.rising_queries:
            lines.append(f"  rising: {', '.join(item.rising_queries[:8])}")
        if item.related_queries:
            lines.append(f"  related: {', '.join(item.related_queries[:8])}")
    return "\n".join(lines)


def _format_reddit_block(raw: RawTrends) -> str:
    if not raw.reddit_posts:
        return ""
    lines = [
        f"- r/{p.subreddit}: {p.title} ({p.score} upvotes, {p.num_comments} comments)"
        for p in raw.reddit_posts[:25]
    ]
    return "\n".join(lines)
