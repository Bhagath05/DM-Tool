"""Per-content-type prompts.

All four prompts share the same system instruction and the same context
fragments (business + trends) — only the task-specific section and the
output schema differ.
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.copy.creative_brief import (
    CREATIVE_BRIEF_INSTRUCTION,
    render_recommendation_context_block,
)
from aicmo.modules.content.schemas import ContentType
from aicmo.modules.content.templates import (
    effective_tone,
    render_business_block,
    render_trend_block,
)
from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

SYSTEM_PROMPT = (
    """You are a senior PERFORMANCE marketer and agency copywriter generating \
native, platform-aware content optimised for CLICKS and LEAD CAPTURE — not vanity \
engagement. Every piece must:
- Start with a complete `creative_brief` (objective, audience, hook, offer, cta, \
visual_direction, platform) — the brief drives all copy below.
- Earn the scroll in the first line / first 2 seconds.
- Open a curiosity gap: the post promises a payoff, the linked landing page \
delivers it.
- Sound like the brand's tone, not generic AI copy.
- Tie back to a real trend or audience insight (no fabrications).
- Treat the CTA as the most important line in the piece. The CTA is verb-led, \
specific, and tied directly to the landing-page promise. Use concrete \
outcome language ("Get the 10-min playbook", "Snag the free template").
- Provide 2-3 CTA variants in `cta_variants` — same intent as the primary, \
different angles (curiosity / urgency / social proof / value reveal). For \
A/B testing.
- Include the strategy explanation the schema asks for — that's how the user \
trusts the piece, so be specific (name the trend, name the lever).

"""
    + CREATIVE_BRIEF_INSTRUCTION
    + "\n"
    + TONE_GUARDRAILS
)


_TYPE_INSTRUCTIONS: dict[ContentType, str] = {
    "social_post": (
        "Write ONE platform-native social post. Match the platform's typical "
        "length and rhythm. Hashtags should mix broad + niche; avoid spammy "
        "stacks. The CTA must be specific (not 'check the link in bio')."
    ),
    "reel": (
        "Design a short-form video (Reel / Short / TikTok). Hook in 0-2 seconds. "
        "Beats are scene-by-scene direction with label + description. "
        "`voiceover_script` is the FULL narration an editor can record or TTS. "
        "on_screen_text mirrors overlays (max 8 lines). Caption goes below the video. "
        "Optional `veo_prompt`: one copy-paste generative video prompt for Veo."
    ),
    "carousel": (
        "Design a carousel (Instagram / LinkedIn). Cover earns the swipe. "
        "Every slide MUST have `title` (headline) AND `body`. "
        "Include `image_prompt` per slide — copy-paste ready for GPT Image / Flux / Midjourney. "
        "Include a dedicated `cta_slide` as the final slide. 4-10 content slides plus CTA."
    ),
    "landing_page_copy": (
        "Write landing page copy that converts cold traffic to leads. "
        "headline + subheadline above the fold, hero_paragraph, 3-6 benefits, "
        "cta_text for the button, form_intro above the form. "
        "Align every line with the creative_brief offer and CTA."
    ),
    "ad_copy": (
        "Write paid ad copy (Meta / Google). Lead with the strongest benefit. "
        "Use a sanctioned CTA button label. targeting_note tells the marketer "
        "who to put this in front of."
    ),
    "blog_article": (
        "Write a complete, SEO-optimised blog article. Title earns the click and "
        "contains the primary keyword. meta_description ≤160 chars. 3-10 body "
        "sections with clear H2 headings and scannable paragraphs — genuinely "
        "useful, specific to this business, never generic filler. Weave the "
        "primary + secondary keywords naturally (no stuffing). Close with a CTA. "
        "Estimate an honest reading_time_minutes from the length."
    ),
    "email": (
        "Write a marketing email. Provide 2-4 A/B subject lines (≤60 chars, no "
        "clickbait), a preview_text preheader, a personalised greeting using "
        "{{first_name}}, a skimmable body built around ONE idea and ONE ask, and "
        "a specific CTA. Do NOT invent a URL — cta_url_hint names where it points. "
        "Match the goal: a nurture/campaign email warms an existing list; a cold "
        "email is short, respectful, and leads with relevance."
    ),
    "product_description": (
        "Write conversion product copy. tagline is a one-line hook. "
        "short_description suits a listing/card; long_description is the full "
        "benefit-led pitch. key_features are benefit-framed (feature → what it "
        "means for the buyer), not spec dumps. End with a purchase-intent CTA."
    ),
    "press_release": (
        "Write a professional press release in standard format: newsworthy "
        "headline, supporting subheadline, dateline, a lead paragraph answering "
        "who/what/when/where/why, 2-6 body paragraphs INCLUDING at least one "
        "quote attributed to a named role (use a placeholder like "
        "'[Founder Name], CEO'), a company boilerplate, and a media_contact block "
        "with placeholder name/email — never fabricate real contact details."
    ),
    # ---- Part 2: story / proof ----
    "case_study": (
        "Write a customer case study: challenge → solution → results. Anonymise "
        "the client (client_descriptor, e.g. 'a mid-market B2B SaaS'). Results are "
        "concrete outcome bullets. Include one illustrative quote attributed to a "
        "placeholder role. Never invent a real company name or fabricated metric "
        "you can't support — frame results as representative outcomes."
    ),
    "customer_story": (
        "Write a narrative customer success story — same structure as a case study "
        "but warmer and story-first (the customer is the hero, the product is the "
        "guide). Anonymise the client; keep outcomes representative, not fabricated."
    ),
    "testimonial": (
        "Write a believable, specific testimonial in the customer's voice "
        "(illustrative — clearly a sample, attributed to '[Name], [role]'). It "
        "names a concrete before/after, not vague praise. Provide a few variants."
    ),
    "product_comparison": (
        "Write an honest product/category comparison. List the criteria that "
        "matter, our genuine strengths, and honest tradeoffs where an alternative "
        "may fit better (this builds trust). End with a clear verdict + CTA. Never "
        "fabricate competitor facts."
    ),
    "faq": (
        "Write an FAQ that answers the real objections + questions this audience "
        "has before buying. 4-12 Q&A pairs, plain answers, each removing a specific "
        "point of friction. Weave in relevant keywords naturally."
    ),
    # ---- Part 2: web page copy (shared WebPageCopyFull) ----
    "website_copy": (
        "Write general website page copy: a clear headline + subheadline, 2-10 "
        "benefit-led sections, and a CTA. Include an SEO title (≤60 chars) and meta "
        "description (≤160). Scannable, specific to this business."
    ),
    "homepage_copy": (
        "Write homepage copy: an above-the-fold headline that states the core value "
        "in one line, a supporting subheadline, sections for how-it-works / social "
        "proof / benefits, and a primary CTA. SEO title + meta included."
    ),
    "about_us": (
        "Write an About page: the origin/mission, what the business believes, who "
        "it serves, and why it's credible — human and specific, not corporate "
        "filler. Sections + a soft CTA. SEO title + meta included."
    ),
    "service_page": (
        "Write a service page: headline naming the service + outcome, sections for "
        "what's included / who it's for / how it works / proof, and a booking CTA. "
        "SEO title + meta included."
    ),
    "sales_page": (
        "Write a long-form sales page: strong headline + subheadline, "
        "problem/agitation, the offer + benefits, objection handling, and a "
        "high-intent CTA. Sections build the argument top to bottom. SEO title + "
        "meta included."
    ),
    # ---- Part 2: email variants (shared EmailFull) ----
    "email_newsletter": (
        "Write a value-first newsletter email to an existing list: subject lines, "
        "preheader, a warm greeting, a skimmable body delivering ONE useful idea, "
        "and a soft CTA. cta_url_hint names where it points."
    ),
    "cold_email": (
        "Write a short, respectful cold outreach email: subject lines that earn the "
        "open without clickbait, one line of genuine relevance to the recipient, a "
        "single clear ask, and an easy CTA. Keep it tight — no fabricated claims."
    ),
    "followup_email": (
        "Write a follow-up email that adds NEW value (not just 'bumping this'): "
        "reference the prior touch, give one fresh reason to act, and restate a "
        "low-friction CTA."
    ),
    "promo_email": (
        "Write a promotional email for an offer: subject lines that convey the "
        "value + a touch of urgency (honest, no fake scarcity), a body that leads "
        "with the benefit, and a strong CTA. cta_url_hint names the offer page."
    ),
    # ---- Part 2: video scripts (shared ReelFull) ----
    "video_script": (
        "Write a short-form video script (general). Hook in the first 2 seconds, "
        "scene-by-scene beats, a full voiceover_script, on-screen text overlays, and "
        "a caption. Optional veo_prompt for generative video."
    ),
    "shorts_script": (
        "Write a YouTube Shorts script: vertical, 15-60s, a pattern-interrupt hook, "
        "fast beats, voiceover + overlays, and a subscribe/CTA end card."
    ),
    "tiktok_script": (
        "Write a TikTok script: native, trend-aware, hook in 0-2s, punchy beats "
        "with on-screen text, spoken voiceover, and a comment-baiting CTA. Keep it "
        "authentic, not ad-like."
    ),
    # ---- Part 2: platform copy ----
    "youtube_title": (
        "Generate YouTube video titles: `primary` is the strongest, `variants` are "
        "3-12 alternatives. ≤70 chars, front-load the keyword + the payoff, avoid "
        "clickbait that the video can't deliver."
    ),
    "youtube_description": (
        "Write a full YouTube description: a keyword-aware first 2 lines (what's "
        "shown before 'more'), a scannable body, relevant hashtags, and a CTA. No "
        "fabricated links — describe where the CTA points."
    ),
    "pinterest_description": (
        "Generate Pinterest pin descriptions: `primary` + `variants`. Keyword-rich, "
        "helpful, ≤500 chars, with a clear reason to click through."
    ),
    "x_thread": (
        "Write an X (Twitter) thread: hook_tweet earns the unroll, 3-15 body tweets "
        "each ≤280 chars carrying ONE idea, and a cta_tweet. Punchy, no filler, "
        "one thought per tweet."
    ),
    # ---- Part 2: micro-copy option sets (shared MicroCopyListFull) ----
    "cta_variations": (
        "Generate CTA button/line variations: `primary` + 3-12 `variants` across "
        "distinct angles (curiosity / urgency / value reveal / social proof). "
        "Verb-led, specific, ≤6 words where possible."
    ),
    "headlines": (
        "Generate headline options: `primary` + variants. Different angles "
        "(benefit, curiosity, objection, outcome). Specific, scannable, no clickbait."
    ),
    "taglines": (
        "Generate brand/product taglines: `primary` + variants. Short, memorable, "
        "true to the brand — capture the core promise in a few words."
    ),
    "hooks": (
        "Generate opening hooks (first line / first 2 seconds): `primary` + "
        "variants. Each opens a curiosity gap or names a sharp pain/benefit."
    ),
    "meta_description": (
        "Generate SEO meta descriptions: `primary` + variants, each ≤160 chars, "
        "including the primary keyword + a reason to click. usage_note explains "
        "which to test."
    ),
    "seo_title": (
        "Generate SEO page titles: `primary` + variants, ≤60 chars, keyword "
        "front-loaded, click-worthy but accurate."
    ),
    # ---- Part 2: keyword ideas ----
    "keyword_ideas": (
        "Generate keyword ideas for the seed_topic: 5-30 keywords, each tagged with "
        "search intent (informational/commercial/transactional/navigational) and an "
        "HONEST priority (high/medium/low) based on fit + specificity. Do NOT "
        "invent search-volume numbers you can't know."
    ),
}


def build_user_prompt(
    *,
    content_type: ContentType,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    platform: str,
    goal: str,
    tone_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> str:
    tone = effective_tone(profile.brand_tone, tone_override)
    instructions = _TYPE_INSTRUCTIONS[content_type]
    context_prefix = (
        render_context_block(context) + "\n\n" if context is not None else ""
    )
    rec_block = render_recommendation_context_block(recommendation_context)

    return f"""{context_prefix}{rec_block}# Task
Generate a {content_type.replace('_', ' ')} for {platform}.

Campaign goal: {goal}
Voice to use: {tone}

{instructions}

# Business context
{render_business_block(profile)}

# Trend context
{render_trend_block(trend_analysis)}

# Requirements
- The platform field of the request was: {platform}. Use platform-native conventions.
- Output must match the response schema exactly.
- Fill `strategy.trend_influence` with the SPECIFIC topic/signal you used (or "none" if no trends were available).
- Fill `strategy.audience_angle` with the SPECIFIC psychology lever (FOMO, status, identity, curiosity, savings, belonging, etc).
"""
