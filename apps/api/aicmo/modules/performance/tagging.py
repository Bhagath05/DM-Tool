"""Phase 9.1 — Creative-tag resolution.

Every generation service (visuals / content / ads) calls
`resolve_creative_tags()` to derive the seven Performance Intelligence
tags from the existing generation inputs. Tags are persisted on the
creative row at creation time so the rollup engine can attribute
outcomes back to tag combinations without joining strategy blobs.

This module is intentionally permissive — it never raises. The seven
tag columns are nullable; if we can't infer one, we leave it NULL.
The Performance engine treats NULL tags as "untagged" rather than
erroring.

Design choice: classify by simple rules now, not by an LLM call. We
already have the inputs in plain form (audience text, goal text,
brand_tone, platform, funnel_stage). Classification cost should not
multiply per generation.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Platform = Literal[
    "meta", "google", "linkedin", "tiktok", "youtube", "other"
]
FunnelStage = Literal["awareness", "consideration", "conversion", "retention"]
OfferType = Literal[
    "discount",
    "free_trial",
    "consultation",
    "bundle",
    "promotion",
    "seasonal",
    "none",
]


class CreativeTags(TypedDict, total=False):
    concept_family: str | None
    emotion: str | None
    audience: str | None
    funnel_stage: FunnelStage | None
    business_goal: str | None
    offer_type: OfferType | None
    # `platform` is already a first-class column on each creative table;
    # we surface it here for completeness but the caller passes it
    # straight through.
    platform: Platform | None


# ---------------------------------------------------------------------
#  Keyword groups — first hit wins inside a single classifier
# ---------------------------------------------------------------------

_CONCEPT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("transformation", ("before and after", "transformation", "results", "change")),
    ("family_experience", ("family", "kids", "parents", "together")),
    ("authority", ("expert", "certified", "founder", "trusted", "professional")),
    ("scarcity", ("limited", "last chance", "ending", "today only")),
    ("social_proof", ("review", "testimonial", "loved", "rated")),
    ("how_to", ("how to", "tutorial", "step-by-step", "guide")),
    ("behind_the_scenes", ("behind the scenes", "process", "making of")),
    ("storytelling", ("story", "journey", "founder story", "narrative")),
    ("comparison", ("vs", "versus", "compared", "alternative")),
    ("question_hook", ("did you know", "have you", "what if", "?")),
]

_EMOTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("warmth", ("family", "love", "care", "welcome", "together")),
    ("curiosity", ("did you know", "secret", "surprising", "why")),
    ("aspiration", ("dream", "imagine", "future", "grow", "achieve")),
    ("urgency", ("now", "today", "last chance", "limited")),
    ("trust", ("trusted", "proven", "expert", "guarantee")),
    ("humor", ("funny", "laugh", "joke")),
    ("excitement", ("exciting", "new", "launch", "wow")),
    ("relief", ("solve", "fix", "stop worrying", "no more")),
]

_OFFER_KEYWORDS: list[tuple[OfferType, tuple[str, ...]]] = [
    ("discount", ("% off", "discount", "save", "sale")),
    ("free_trial", ("free trial", "try free", "no risk")),
    ("consultation", ("free consultation", "free call", "book a call", "free audit")),
    ("bundle", ("bundle", "combo", "package deal")),
    ("seasonal", ("holiday", "diwali", "christmas", "festival", "season")),
    ("promotion", ("promo", "special offer", "launch offer")),
]

_FUNNEL_KEYWORDS: list[tuple[FunnelStage, tuple[str, ...]]] = [
    ("awareness", ("awareness", "brand", "introduce", "reach")),
    ("consideration", ("compare", "evaluate", "learn", "research")),
    ("conversion", ("buy", "book", "sign up", "order", "subscribe", "purchase", "lead")),
    ("retention", ("loyalty", "repeat", "renew", "come back", "members")),
]


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


def _first_match(haystack: str, groups) -> str | None:
    h = haystack.lower()
    for label, words in groups:
        for w in words:
            if w in h:
                return label
    return None


def _audience_slug(audience_text: str | None) -> str | None:
    """Compact audience identifier from free text — first 5 meaningful
    words, snake-cased, capped at 96 chars."""
    if not audience_text:
        return None
    cleaned = "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in audience_text.lower()
    )
    parts = [p for p in cleaned.split() if len(p) > 2][:6]
    if not parts:
        return None
    return "_".join(parts)[:96]


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def resolve_creative_tags(
    *,
    goal: str | None = None,
    audience: str | None = None,
    platform: str | None = None,
    funnel_stage: str | None = None,
    business_goal: str | None = None,
    offer_hint: str | None = None,
    strategy_text: str | None = None,
    tone: str | None = None,
) -> CreativeTags:
    """Best-effort classifier. Never raises; returns a dict with all
    keys present (values may be None).

    `strategy_text` is the concatenation of any LLM-emitted strategy
    blurbs (hook + audience_angle + why_it_works). The richer the
    input, the better the classifier.
    """
    haystack_parts = [
        goal or "",
        strategy_text or "",
        audience or "",
        offer_hint or "",
        tone or "",
        business_goal or "",
    ]
    haystack = " ".join(p for p in haystack_parts if p)

    concept_family = _first_match(haystack, _CONCEPT_KEYWORDS) if haystack else None
    emotion = _first_match(haystack, _EMOTION_KEYWORDS) if haystack else None
    offer_type: OfferType = (
        _first_match(haystack, _OFFER_KEYWORDS) or "none"  # type: ignore[assignment]
    )

    # funnel_stage: explicit input wins; otherwise infer from text.
    funnel_normalised: FunnelStage | None = None
    explicit = (funnel_stage or "").strip().lower()
    if explicit in {"awareness", "consideration", "conversion", "retention"}:
        funnel_normalised = explicit  # type: ignore[assignment]
    else:
        funnel_normalised = _first_match(haystack, _FUNNEL_KEYWORDS)  # type: ignore[assignment]

    # platform: pass-through, normalised to our enum if recognisable.
    plat = (platform or "").lower().strip()
    if plat in {"facebook", "ig", "instagram", "meta", "fb"}:
        plat_norm: Platform = "meta"
    elif plat in {"google", "google ads", "adwords", "search"}:
        plat_norm = "google"
    elif plat in {"linkedin", "li"}:
        plat_norm = "linkedin"
    elif plat in {"tiktok", "tt"}:
        plat_norm = "tiktok"
    elif plat in {"youtube", "yt"}:
        plat_norm = "youtube"
    elif plat:
        plat_norm = "other"
    else:
        plat_norm = None  # type: ignore[assignment]

    return CreativeTags(
        concept_family=concept_family,
        emotion=emotion,
        audience=_audience_slug(audience),
        funnel_stage=funnel_normalised,
        business_goal=((business_goal or goal or "")[:96] or None),
        offer_type=offer_type,
        platform=plat_norm,
    )
