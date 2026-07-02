from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aicmo.copy.creative_brief import MarketingCreativeBrief
from aicmo.security.prompt_safety import sanitize_prompt_input

ContentType = Literal[
    # Original social/ad/landing types.
    "social_post",
    "reel",
    "carousel",
    "ad_copy",
    "landing_page_copy",
    # Phase 6.2 Part 1 — written / long-form.
    "blog_article",
    "email",
    "product_description",
    "press_release",
    # Phase 6.2 Part 2 — full content-type coverage (shared schemas, distinct prompts).
    "case_study",
    "customer_story",
    "testimonial",
    "product_comparison",
    "faq",
    "website_copy",
    "homepage_copy",
    "about_us",
    "service_page",
    "sales_page",
    "email_newsletter",
    "cold_email",
    "followup_email",
    "promo_email",
    "youtube_title",
    "youtube_description",
    "video_script",
    "shorts_script",
    "tiktok_script",
    "pinterest_description",
    "x_thread",
    "cta_variations",
    "headlines",
    "taglines",
    "hooks",
    "meta_description",
    "seo_title",
    "keyword_ideas",
]

CONTENT_TYPES: tuple[ContentType, ...] = get_args(ContentType)

# Types NOT gated by the preferred-platform check (written/web/email/micro-copy/
# scripts — generated for a site/inbox/doc, or a platform the user needn't have
# pre-configured). The original social-feed types keep the check.
_PLATFORM_GATED: frozenset[str] = frozenset(
    {"social_post", "reel", "carousel", "ad_copy"}
)
NON_PLATFORM_TYPES: frozenset[str] = frozenset(
    ct for ct in CONTENT_TYPES if ct not in _PLATFORM_GATED
)


# ---------- Shared "why-it-works" envelope ----------


class ContentStrategy(BaseModel):
    """The strategist explanation that ships with every generated piece.

    This is what makes the engine feel like an AI marketing strategist rather
    than a generic writer. Every type-specific schema below includes this.
    """

    trend_influence: str = Field(
        description="Which specific trend / signal from the report this leans on, "
        "or 'none — grounded in profile only' if no trends were available.",
    )
    audience_angle: str = Field(
        description="Which audience psychology lever this targets (FOMO, status, "
        "curiosity, identity, savings, belonging, etc.) and why it fits.",
    )
    strategy_note: str = Field(
        description="One short paragraph explaining why this piece will work for "
        "this business on this platform right now.",
    )


# ---------- Per-content-type AI output schemas ----------
# Each one nests ContentStrategy so we get strategy + content in ONE Gemini call.


class SocialPostFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    hook: str = Field(description="First line / opening that earns the scroll.")
    body: str = Field(description="Main post body, platform-native length.")
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, specific, ties to the landing-page promise.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings. Same intent as primary, different angles "
        "(curiosity / urgency / social proof / value reveal). For A/B testing.",
    )


class ReelBeat(BaseModel):
    label: str = Field(description="Beat label, e.g. 'Hook', 'Reveal', 'Payoff'.")
    description: str = Field(description="What happens visually in 1-2 sentences.")


class ReelFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    hook: str = Field(description="0-2 second hook script + visual.")
    beats: list[ReelBeat] = Field(min_length=3, max_length=6)
    voiceover_script: str = Field(
        min_length=20,
        description="Full voiceover narration — publish-ready for editor/TTS.",
    )
    on_screen_text: list[str] = Field(
        min_length=2, max_length=8, description="Captions/overlays in order."
    )
    caption: str
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, conversion-focused.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings for A/B testing.",
    )
    veo_prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional copy-paste video prompt for Veo / Runway-style tools.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_reel(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("reel", data)
        return data


class CarouselSlide(BaseModel):
    title: str = Field(description="Slide headline — required on every slide.")
    body: str = Field(description="Slide body, max ~40 words.")
    image_prompt: str | None = Field(
        default=None,
        max_length=1500,
        description="Copy-paste image prompt for this slide (Flux, Midjourney, GPT Image).",
    )


class CarouselFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    cover_title: str = Field(description="Slide-1 cover that earns a swipe.")
    slides: list[CarouselSlide] = Field(min_length=4, max_length=10)
    cta_slide: CarouselSlide = Field(
        description="Final slide — dedicated CTA with headline + action copy."
    )
    caption: str
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, conversion-focused.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings for A/B testing.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_carousel(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("carousel", data)
        return data


class LandingBenefit(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=10, max_length=400)


class LandingPageCopyFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str = Field(min_length=4, max_length=160)
    subheadline: str = Field(min_length=10, max_length=400)
    hero_paragraph: str = Field(
        min_length=20,
        max_length=800,
        description="Above-the-fold body copy — benefit-led, scannable.",
    )
    benefits: list[LandingBenefit] = Field(min_length=3, max_length=6)
    cta_text: str = Field(min_length=2, max_length=40)
    form_intro: str = Field(
        min_length=10,
        max_length=200,
        description="One line above the lead form.",
    )
    social_proof_line: str | None = Field(default=None, max_length=200)
    privacy_blurb: str | None = Field(default=None, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _coerce_landing(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("landing_page_copy", data)
        return data


class AdCopyFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str = Field(description="Ad headline, ≤40 chars where possible.")
    primary_text: str = Field(description="Main ad body, conversion-focused.")
    description: str = Field(description="Short supporting line, ≤90 chars.")
    cta_button: str = Field(
        description="One of: Learn More, Shop Now, Sign Up, Get Quote, Book Now, "
        "Download, Subscribe, Contact Us, Get Offer."
    )
    targeting_note: str = Field(
        description="Who this ad should be targeted to (1-2 sentences)."
    )


# ---------- Phase 6.2 written / long-form types ----------


class BlogSection(BaseModel):
    heading: str = Field(description="Section H2 heading.")
    body: str = Field(description="Section body, 2-5 short paragraphs, scannable.")


class BlogArticleFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    title: str = Field(description="SEO-friendly, compelling article title.")
    slug: str = Field(description="URL slug, lowercase-hyphenated.")
    meta_description: str = Field(
        max_length=200,
        description="SEO meta description ≤160 chars — includes the primary keyword.",
    )
    primary_keyword: str = Field(description="The main keyword this article ranks for.")
    secondary_keywords: list[str] = Field(
        default_factory=list, max_length=10, description="Supporting keywords / entities."
    )
    intro: str = Field(description="Opening 1-2 paragraphs that hook + set the promise.")
    sections: list[BlogSection] = Field(
        min_length=3, max_length=10, description="Body sections with H2 headings."
    )
    conclusion: str = Field(description="Closing that reinforces the takeaway + leads to the CTA.")
    cta: str = Field(description="Primary call to action for the reader.")
    reading_time_minutes: int = Field(ge=1, le=60)


class EmailFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    subject_lines: list[str] = Field(
        min_length=2, max_length=4, description="A/B-ready subject lines, ≤60 chars each."
    )
    preview_text: str = Field(max_length=140, description="Inbox preheader line.")
    greeting: str = Field(description="Personalised opener, e.g. 'Hi {{first_name}},'.")
    body: str = Field(description="Email body — plain, skimmable, one clear idea.")
    cta: str = Field(description="Primary CTA — verb-led, specific.")
    cta_url_hint: str = Field(
        description="Where the CTA should point (page/offer), plain text — no fabricated URL."
    )
    ps_line: str | None = Field(default=None, description="Optional P.S. reinforcing the offer.")


class ProductDescriptionFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    title: str = Field(description="Product name / title as it should appear.")
    tagline: str = Field(max_length=120, description="One-line hook.")
    short_description: str = Field(description="1-2 sentence summary for listings.")
    long_description: str = Field(description="Full benefit-led description, scannable.")
    key_features: list[str] = Field(
        min_length=3, max_length=8, description="Benefit-framed feature bullets."
    )
    cta: str = Field(description="Buy / add-to-cart style CTA.")


class PressReleaseFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str = Field(description="Announcement headline, newsworthy + specific.")
    subheadline: str = Field(description="Supporting deck line under the headline.")
    dateline: str = Field(description="CITY, State — Month Day, Year format (placeholder ok).")
    lead_paragraph: str = Field(description="Who/what/when/where/why in the first paragraph.")
    body_paragraphs: list[str] = Field(
        min_length=2, max_length=6, description="Supporting paragraphs incl. a quote."
    )
    boilerplate: str = Field(description="About-the-company standard paragraph.")
    media_contact: str = Field(
        description="Contact block — name/role/email placeholders; no fabricated real contact."
    )


# ---------- Phase 6.2 (Part 2) — shared schemas for structurally-similar types ----------
# One schema, many content_types, DISTINCT prompts (per the 'reuse schemas, never
# duplicate templates' rule). SCHEMA_BY_TYPE maps each type to the right shape;
# _TYPE_INSTRUCTIONS gives each its own task guidance.


class MicroCopyListFull(BaseModel):
    """Short-copy option sets: headlines, taglines, hooks, CTAs, SEO/meta titles,
    YouTube titles, Pinterest descriptions."""

    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    primary: str = Field(description="The single strongest option.")
    variants: list[str] = Field(
        min_length=3, max_length=12, description="Alternative options, distinct angles."
    )
    usage_note: str = Field(description="When/where to use these + how to A/B them.")


class KeywordIdea(BaseModel):
    keyword: str
    intent: Literal["informational", "commercial", "transactional", "navigational"]
    priority: Literal["high", "medium", "low"] = Field(
        description="Honest priority from fit + specificity — NOT a fabricated search volume."
    )


class KeywordIdeasFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    seed_topic: str
    keywords: list[KeywordIdea] = Field(min_length=5, max_length=30)


class WebPageSection(BaseModel):
    heading: str
    body: str


class WebPageCopyFull(BaseModel):
    """Full website page copy: website/homepage/about/service/sales pages."""

    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str
    subheadline: str
    sections: list[WebPageSection] = Field(min_length=2, max_length=10)
    cta_text: str = Field(max_length=40)
    seo_title: str = Field(max_length=70, description="≤60 chars ideally, includes the topic.")
    meta_description: str = Field(max_length=200, description="SEO meta ≤160 chars.")


class CaseStudyFull(BaseModel):
    """Case study / customer story."""

    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    title: str
    client_descriptor: str = Field(description="Anonymised client type — no fabricated real name.")
    challenge: str
    solution: str
    results: list[str] = Field(min_length=2, max_length=6, description="Outcome bullets.")
    quote: str = Field(description="A representative quote attributed to a placeholder role.")
    cta: str


class TestimonialFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    quote: str = Field(description="A believable testimonial in the customer's voice (illustrative).")
    attribution: str = Field(description="[Name], [role/company] placeholders — never a fabricated real person.")
    context: str = Field(description="What prompted it — the before/after.")
    variants: list[str] = Field(default_factory=list, max_length=4)


class FaqItem(BaseModel):
    question: str
    answer: str


class FaqFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    items: list[FaqItem] = Field(min_length=4, max_length=12)


class ProductComparisonFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    intro: str
    criteria: list[str] = Field(min_length=3, max_length=8, description="Comparison dimensions.")
    our_strengths: list[str] = Field(min_length=2, max_length=6)
    honest_tradeoffs: list[str] = Field(
        default_factory=list, description="Where an alternative may fit better — honest, builds trust."
    )
    verdict: str
    cta: str


class XThreadFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    hook_tweet: str = Field(max_length=280, description="Tweet 1 — earns the unroll.")
    tweets: list[str] = Field(min_length=3, max_length=15, description="Body tweets, ≤280 each.")
    cta_tweet: str = Field(max_length=280)
    hashtags: list[str] = Field(default_factory=list, max_length=5)


class YouTubeDescriptionFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    description: str = Field(description="Full YouTube description, keyword-aware, scannable.")
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    cta: str


# ---------- API request / response ----------

PRESET_GOALS: tuple[str, ...] = (
    "Drive engagement",
    "Build brand awareness",
    "Drive conversions / sales",
    "Educate the audience",
    "Promote a launch",
    "Grow email list",
    "Establish thought leadership",
)


class GenerateRequest(BaseModel):
    content_type: ContentType
    platform: str = Field(min_length=2, max_length=64)
    goal: str = Field(min_length=2, max_length=255)
    tone: str | None = Field(
        default=None,
        max_length=64,
        description="Override of the brand tone for this single piece.",
    )
    recommendation_context: str | None = Field(
        default=None,
        max_length=600,
        description="Optional intelligence recommendation observation + action.",
    )
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Attach this asset to a published lead page — the generated "
        "CTAs and share URL will point there with full attribution.",
    )
    # Phase 6.2 — optional traceability links (each validated against the tenant's
    # brand before persisting; cross-tenant IDs are rejected).
    campaign_id: uuid.UUID | None = Field(default=None)
    bundle_id: uuid.UUID | None = Field(default=None)
    strategy_id: uuid.UUID | None = Field(default=None)
    recommendation_id: uuid.UUID | None = Field(default=None)

    # Phase S2.5 — sanitise free-text fields before the prompt composer.
    @field_validator("goal", "recommendation_context", mode="before")
    @classmethod
    def _scrub_prompt_inputs(cls, v):
        return sanitize_prompt_input(v, field_name="content_request")


class UpdateRequest(BaseModel):
    is_saved: bool


class GeneratedContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    trend_report_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    # Phase 6.2 — traceability links.
    campaign_id: uuid.UUID | None = None
    bundle_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None
    recommendation_id: uuid.UUID | None = None
    content_type: ContentType
    platform: str
    goal: str
    tone: str
    strategy: ContentStrategy
    # Free-form dict because the shape depends on content_type. The frontend
    # branches on content_type to render the right component.
    output: dict[str, Any]
    # Computed at response time — landing-page URL with UTM + attribution.
    # None if no landing page is attached.
    share_url: str | None = None
    is_saved: bool
    created_at: datetime
    updated_at: datetime


class GeneratedContentList(BaseModel):
    items: list[GeneratedContentResponse]


# Dispatch table consumed by generator.py — keeps content_type → schema in one place.
SCHEMA_BY_TYPE: dict[ContentType, type[BaseModel]] = {
    "social_post": SocialPostFull,
    "reel": ReelFull,
    "carousel": CarouselFull,
    "ad_copy": AdCopyFull,
    "landing_page_copy": LandingPageCopyFull,
    "blog_article": BlogArticleFull,
    "email": EmailFull,
    "product_description": ProductDescriptionFull,
    "press_release": PressReleaseFull,
    # Part 2 — story/proof.
    "case_study": CaseStudyFull,
    "customer_story": CaseStudyFull,
    "testimonial": TestimonialFull,
    "product_comparison": ProductComparisonFull,
    "faq": FaqFull,
    # Part 2 — web page copy (shared shape).
    "website_copy": WebPageCopyFull,
    "homepage_copy": WebPageCopyFull,
    "about_us": WebPageCopyFull,
    "service_page": WebPageCopyFull,
    "sales_page": WebPageCopyFull,
    # Part 2 — email variants (reuse EmailFull).
    "email_newsletter": EmailFull,
    "cold_email": EmailFull,
    "followup_email": EmailFull,
    "promo_email": EmailFull,
    # Part 2 — video scripts (reuse ReelFull).
    "video_script": ReelFull,
    "shorts_script": ReelFull,
    "tiktok_script": ReelFull,
    # Part 2 — platform micro/long copy.
    "youtube_title": MicroCopyListFull,
    "youtube_description": YouTubeDescriptionFull,
    "pinterest_description": MicroCopyListFull,
    "x_thread": XThreadFull,
    # Part 2 — micro-copy option sets (shared shape).
    "cta_variations": MicroCopyListFull,
    "headlines": MicroCopyListFull,
    "taglines": MicroCopyListFull,
    "hooks": MicroCopyListFull,
    "meta_description": MicroCopyListFull,
    "seo_title": MicroCopyListFull,
    # Part 2 — SEO keyword ideas.
    "keyword_ideas": KeywordIdeasFull,
}


# Used to split the AI's nested response into strategy + output for storage.
def split_strategy(
    content_type: ContentType, payload: BaseModel
) -> tuple[ContentStrategy, dict[str, Any]]:
    dumped = payload.model_dump(mode="json")
    strategy = ContentStrategy.model_validate(dumped.pop("strategy"))
    return strategy, dumped


# Re-export so the router can use the alias in OpenAPI.
GeneratedAt = Annotated[datetime, Field(description="Server-assigned timestamp.")]
