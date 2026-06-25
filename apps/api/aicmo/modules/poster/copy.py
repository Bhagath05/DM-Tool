"""Turn a topic into art direction + copy for ONE LinkedIn post.

The model chooses the layout, palette mood, and image style, and — most
importantly — writes an `image_concept` that SHOWS what the business does
(the visual carries the meaning). Plus the headline, subhead, CTA, value
bullets, and the long-form caption.

Primary path: structured LLM output. On any failure / timeout it falls back
to a deterministic composer so the feature always returns something usable.
`clamp()` guarantees every enum value is renderable.
"""

from __future__ import annotations

import asyncio

import structlog

from aicmo.modules.poster.schemas import LinkedInCopy

log = structlog.get_logger()

_LAYOUTS = {"editorial", "split", "banner"}
_PALETTES = {"warm", "cool", "bold", "mono"}
_STYLES = {"photo", "illustration"}

_SYSTEM = """You are a senior B2B social designer + copywriter. From a topic you \
produce the ART DIRECTION and copy for ONE professional LinkedIn post that \
looks UNIQUE and clearly reflects the business — never a generic icon diagram.

Decisions you make:
- image_concept: the single most important field. Describe ONE hero image that \
SHOWS what this business actually does — a concrete subject, setting, lighting \
and mood an image model can render. A cafe → its food/drinks; a gym → people \
training; a SaaS → a clean device/abstract UI scene; a law firm → a refined \
office detail. The image must contain NO text, words, letters, or logos.
- image_style: "photo" for real-world/physical businesses; "illustration" for \
software, finance, or abstract concepts.
- layout: "editorial" (one strong subject, full-bleed), "split" (offer with \
2-3 proof points), or "banner" (image on top, summary below). Pick what fits.
- palette: warm / cool / bold / mono — match the mood of the business.

Copy rules:
- headline_lead + headline_accent = a SHORT headline (<= 5 words total); \
headline_accent is the punchy part shown in the brand colour.
- subheadline: one concrete sentence. cta: a short button label (e.g. \
"Order for pickup", "Book a call"). bullets: 0-3 value points <= 32 chars \
(used by split/banner).
- post_body: a real LinkedIn caption, 120-260 words, plain text, strong first \
line, 2-4 short paragraphs, a soft CTA question. No markdown, no hashtags.
- hashtags: 5-8 lowercase tags WITHOUT the # symbol.
No hype, no emojis in the poster fields, no buzzword soup."""


def system_prompt() -> str:
    return _SYSTEM


def user_prompt(topic: str, *, goal: str | None, brand_name: str, context: str | None) -> str:
    parts = [f"Brand: {brand_name}", f"Announcement topic: {topic}"]
    if goal:
        parts.append(f"Primary goal of this post: {goal}")
    if context:
        parts.append(f"Business context (for relevance; do not quote verbatim):\n{context}")
    parts.append("Write the art direction and copy now.")
    return "\n\n".join(parts)


def clamp(copy: LinkedInCopy) -> LinkedInCopy:
    if copy.layout not in _LAYOUTS:
        copy.layout = "editorial"
    if copy.palette not in _PALETTES:
        copy.palette = "bold"
    if copy.image_style not in _STYLES:
        copy.image_style = "photo"
    copy.bullets = [b.strip()[:32] for b in (copy.bullets or []) if b.strip()][:3]
    copy.hashtags = [h.lstrip("#").strip() for h in (copy.hashtags or []) if h.strip()][:8]
    copy.image_concept = (copy.image_concept or "").strip()[:600]
    return copy


async def compose(
    topic: str, *, goal: str | None = None, brand_name: str = "Your Brand", context: str | None = None
) -> tuple[LinkedInCopy, bool]:
    """Return (copy, used_llm). Never raises — falls back deterministically."""
    try:
        from aicmo.llm import get_llm_router
        from aicmo.llm.providers.base import LLMMessage

        router = get_llm_router()
        async with asyncio.timeout(30):
            result = await router.generate(
                response_schema=LinkedInCopy,
                system=system_prompt(),
                messages=[
                    LLMMessage(
                        role="user",
                        content=user_prompt(
                            topic, goal=goal, brand_name=brand_name, context=context
                        ),
                    )
                ],
                temperature=0.8,
                max_tokens=1700,
            )
        log.info("poster.copy.llm", topic=topic[:60], layout=result.data.layout)
        return clamp(result.data), True
    except Exception as exc:  # noqa: BLE001
        log.warning("poster.copy.fallback", error=str(exc)[:160], topic=topic[:60])
        return clamp(_fallback(topic, goal=goal, brand_name=brand_name)), False


# ---------------------------------------------------------------------
#  Deterministic fallback — no network, always works
# ---------------------------------------------------------------------


def _title(s: str, n: int) -> str:
    words = [w for w in s.replace("\n", " ").split() if w]
    return " ".join(words[:n]).title()


def _fallback(topic: str, *, goal: str | None, brand_name: str) -> LinkedInCopy:
    t = topic.strip().rstrip(".")
    accent = _title(t, 2) or "What's New"
    sub = (
        f"{accent} — built to help you {goal.strip()}."
        if goal
        else f"A simpler, better way to {(_title(t, 5) or 'grow your business').lower()}."
    )[:170]
    concept = (
        f"A clean, professional scene that represents '{t}' for {brand_name}: the "
        "real product, place, or people behind it, natural lighting, premium and "
        "inviting mood. No text, words, letters, or logos."
    )[:600]
    body = (
        f"{accent} is here.\n\n"
        f"{sub}\n\n"
        "We built this for people who'd rather get the result than wrestle the "
        "tools. Simple to start, and it shows up where your customers already are.\n\n"
        f"Curious if it fits your world? Drop a comment or DM — happy to walk you through it. — {brand_name}"
    )
    return LinkedInCopy(
        layout="editorial",
        palette="bold",
        image_style="photo",
        image_concept=concept,
        eyebrow="Introducing",
        headline_lead="Meet",
        headline_accent=accent[:28],
        subheadline=sub,
        cta="Learn more",
        bullets=["Quick to set up", "On-brand by default", "Built for results"],
        post_body=body,
        hashtags=["marketing", "smallbusiness", "growth", "branding", "socialmedia"],
    )
