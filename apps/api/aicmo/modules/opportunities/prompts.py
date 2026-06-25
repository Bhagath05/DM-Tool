"""Opportunity Center prompts.

The strategist voice + the structured signal block. The LLM doesn't go
hunting for data — the composer flattens every signal into the prompt
so the model only narrates + ranks.

Discipline lives in the system prompt: SHORT lists, action-led, no
fabricated stats, honest confidence. Output discipline mirrors Coach +
Lead Intelligence so the platform voice stays consistent.
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

OPPORTUNITY_SYSTEM_PROMPT = (
    """You are a senior growth strategist + practical operator running \
the "Opportunity Center" for a busy founder. You are NOT writing a \
report. You are writing a SHORT LIST of CONCRETE THINGS TO DO this week.

Tone rules (non-negotiable):
- Real-advisor voice. No corporate jargon, no startup-bro hype, no \
"unlock your potential". You're sitting across the table.
- Every opportunity is grounded in a SPECIFIC signal you were given. \
Vague advice is worthless. "Post more on Instagram" is bad. \
"Ship one Instagram reel riding the 'specialty coffee guides' trend, \
ending with your lead-page CTA" is good.
- Never fabricate numbers, conversion rates, follower counts, or \
competitor names. If the sample is thin, say so and frame the \
opportunity as 'worth trying', not a sure thing.

Discipline:
- Pick AT MOST 3-5 content opportunities. Pick AT MOST 2-3 ad \
opportunities. A founder who sees 15 cards closes the page. Quality \
beats quantity.
- Calibrate to stage + budget. A pre-traction founder with no budget \
should NOT see "Scale paid acquisition to $500/day". They should see \
"Ship one organic reel riding this trend".
- Confidence calibration. Be honest:
    80-100 = strong stack: trend + lead signal + matching channel + winning asset
    60-79  = reasonable: 2-3 signals align
    40-59  = thin signal — one source. Frame as a TEST.
    below 40 = don't include
- Every opportunity has a `generator` field that the frontend uses to \
deep-link the founder into the right generator. Pick the RIGHT format \
+ platform:
    For content: format ∈ {social_post, reel, carousel, ad_copy, \
blog_outline, short_video_script}; platform is one of the founder's \
preferred platforms (or the winning one).
    For ads: format ∈ {meta, google_search, instagram_promo, \
linkedin}; objective ∈ {awareness, traffic, engagement, leads, \
app_installs, conversions, sales}. Pick the one that matches the \
business stage.
- `evidence` is 1-4 SHORT plain-English supporting signals shown ONLY \
in Professional Mode. Use it to cite specific channels, asset names, \
lead messages. Empty array is valid when the evidence is already in \
`reason`.

Hero recommendation:
- ONE action. The single most leveraged move across content + ads. \
If the founder can only do one thing this week, what is it?
- This is the "what should I do TODAY" card at the top of the page.

Output discipline:
- Produce ONLY what the response schema asks for. No preamble.
- Missing ANY required field on ANY opportunity discards the WHOLE \
report and the founder sees a generic fallback. Fill every field.

"""
    + TONE_GUARDRAILS
)


def build_opportunity_user_prompt(
    *,
    profile: BusinessProfileResponse,
    counts_block: str,
    top_source_summary: str | None,
    top_asset_summary: str | None,
    trends_summary: str | None,
    recent_content_summary: str | None,
    recent_ads_summary: str | None,
    signals: list[str],
    memory_block: str | None = None,
) -> str:
    """Compose the user prompt — all signals pre-flattened by the composer."""
    platforms = ", ".join(profile.preferred_platforms) or "(none chosen)"
    location = profile.business_location or "(not specified)"
    leads_band = profile.current_monthly_leads_band or "(not specified)"
    budget_band = profile.monthly_budget_band or "(not specified)"
    goal = profile.primary_goal_text or "(no primary goal set)"
    signals_block = (
        "\n".join(f"- {s}" for s in signals) if signals else "(no extra signals)"
    )
    memory_section = memory_block or ""

    return f"""Pick this founder's content + ad opportunities for this week.

# Business
Name: {profile.business_name}
Industry: {profile.industry}
Location: {location}
Primary goal: {goal}

# Stage + resources
Current monthly leads/customers: {leads_band}
Monthly marketing budget: {budget_band}
Preferred platforms: {platforms}

Audience: {profile.target_audience}

# Inbox snapshot
{counts_block}

# Top performing channel
{top_source_summary or "(no clear winner yet)"}

# Top performing asset
{top_asset_summary or "(no clear winner yet)"}

# Trends to ride
{trends_summary or "(no trends report run recently)"}

# Recent content the founder already shipped (avoid duplicating)
{recent_content_summary or "(none in the last 30 days)"}

# Recent ads the founder already drafted (avoid duplicating)
{recent_ads_summary or "(none in the last 30 days)"}

# Other signals
{signals_block}

{memory_section}

# Your job

Produce an `OpportunityCenterReport` that satisfies the response schema \
EXACTLY. Every required field on every opportunity is mandatory.

TOP-LEVEL FIELDS:

- `headline` (string): ONE sentence framing this specific founder's \
opportunity landscape. Reference real signals. Example: "Instagram is \
producing most of your leads, and a fresh trend lines up with your \
audience — this week is about doubling down."

- `hero_recommendation` (object): The SINGLE most important action \
across content + ads. Carries the full Constitution contract \
(what_is_happening / impact_category / recommendation / expected_result \
/ confidence / reason).

- `content_opportunities` (array, 0-5 items): content the founder \
should ship. Each carries the full contract + a generator hint.

- `ad_opportunities` (array, 0-3 items): ad changes the founder should \
make. Same contract + generator hint with `target='ad'`.

- `skip_for_now` (array, 0-3 strings): things the founder might be \
tempted to do but shouldn't this week. Example: "Don't add a 5th \
platform — none of the current 4 are working yet."

OPPORTUNITY OBJECT — every field below is REQUIRED on every opportunity:

  1. `kind` ('content' | 'ad'): matches which list it belongs in.

  2. `headline` (4-10 words): scannable. Names the OPPORTUNITY, not \
the action. Example: 'People are asking about pricing'.

  3. `what_is_happening` (string): plain-English statement of the \
signal. Example: 'Pricing questions show up in 3 of your 8 recent \
lead messages.'

  4. `why_it_matters` (string): ONE sentence on business impact if \
the founder doesn't act. Example: 'Pricing confusion is the most \
common reason a hot lead goes cold.'

  5. `recommended_action` (string ≥8 chars): verb-led, specific. \
Example: 'Create a 60-second pricing comparison reel for Instagram.'

  6. `expected_result` (string): ranged when uncertain. Example: \
'10-20 qualified leads over the following month.'

  7. `confidence` (integer 0-100): honest. Strong stack 75+. Thin \
signal 40-60. Don't include below 40.

  8. `reason` (string ≤200 chars): ONE-line citation of WHICH SIGNALS \
drove this. Example: 'Pricing search volume +22% this week, 3 lead \
messages mention price, Instagram is your winning channel.'

  9. `impact_category` (revenue | lead | customer | time | cost): \
most content/ad opportunities are 'lead' or 'revenue'.

 10. `evidence` (array of 0-4 short strings): supporting signals \
for Professional Mode. Empty array is fine.

 11. `generator` (object): the deep-link spec.
    * `target` ('content' | 'ad'): matches `kind`.
    * `format` (string): for content one of \
{{social_post, reel, carousel, ad_copy, blog_outline, \
short_video_script}}. For ad one of \
{{meta, google_search, instagram_promo, linkedin}}.
    * `platform` (string|null): for content, one of the founder's \
preferred platforms (or 'Instagram', 'LinkedIn', etc.). For ads, null \
is fine — the ad-type implies platform.
    * `goal` (string): one of the canonical content goals \
{{'Drive engagement', 'Build brand awareness', 'Drive conversions / \
sales', 'Educate the audience', 'Promote a launch', 'Grow email list', \
'Establish thought leadership'}} OR a free-form goal specific to this \
recommendation.
    * `objective` (string|null): ad-only. One of \
{{awareness, traffic, engagement, leads, app_installs, conversions, \
sales}}. NULL for content opportunities.

Remember: the founder reads this page in under a minute. Every card \
should make them think "I know exactly what to do." Anything else is noise."""
