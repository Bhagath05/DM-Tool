"""Build the natural-language prompt sent to the image provider.

Pure function: brief + business context in → string out. The provider
just renders what we give it; the quality of the render is
overwhelmingly the quality of this prompt.

Phase 8.4 — Creative Diversity Engine.
======================================
Phase 8.3 made the renderer outcome-driven, but consecutive renders
for the same business / goal / audience still tended to look similar
— same scene type, same camera angle, same energy. Phase 8.4 fixes
that by introducing a CONCEPT FAMILY layer between the goal and the
scene. Every render belongs to exactly ONE of twelve canonical
concept families (Customer Transformation, Before vs After, Founder
Story, Customer Testimonial, Social Proof, Product Demonstration,
Behind The Scenes, Authority Positioning, Problem Awareness,
Lifestyle Aspiration, Community, Offer Driven), and the renderer
rotates through them so a founder can ship 20 ads in a row without
the feed feeling repetitive.

Key Phase 8.4 mechanics:

1. **One concept family per render.** A render that says
   "transformation" composes a different scene from one that says
   "social proof" — even when business / goal / audience are
   identical. The family is named in the prompt AND surfaced as a
   short hook line ("Look what changed." / "Everyone is choosing
   this." / etc.) that anchors the composition.

2. **Rotation.** `build_image_prompt` accepts an optional
   `recent_concept_families: tuple[str, ...]` kwarg (most recent
   first). The picker excludes anything in that list before scoring,
   so the next render is guaranteed to break the most-recent
   pattern. The caller (`render.py`) reads the most recent N
   families from prior renders' prompts (via the
   `CONCEPT FAMILY — <slug>` marker the prompt now embeds) and
   passes them in.

3. **Goal-aware preference.** Each goal has a ranked preferred set
   of families (Lead Gen → Problem Awareness > Customer Testimonial
   > Authority; Bookings → Lifestyle > Social Proof > Transformation;
   Brand Awareness → Founder Story > Behind The Scenes > Authority;
   etc.). The picker walks the preferred list in order, skipping
   anything recent, and falls back to the broader 12-family pool
   only if every preferred family was recently used.

4. **Hook engine.** Each family carries a one-line scroll-stop hook
   that names the angle ("Look what changed" / "Imagine this is
   your life" / "Still struggling with this?"). The hook appears in
   the prompt so the diffusion model can compose AROUND the angle
   rather than around generic "premium" energy.

5. **Creative Uniqueness Test.** The conversion gate now closes
   with a sixth test: "Compared to the last 3 renders for this
   business, is this CONCEPT genuinely different — not just the
   same scene with different lighting?" If concept overlap is high,
   the prompt tells the model to re-plan.

6. **Stable parseable marker.** The prompt embeds
   `CONCEPT FAMILY — <slug>` on a dedicated line so `render.py` can
   regex it back out of stored prompts for rotation queries. No
   schema migration needed.

Phase 8.3 — Outcome-Driven Creative Engine.
===========================================
Phase 8.1 made the output look like a real photograph (no AI / 3D /
CGI / cartoon). Phase 8.2 made it conversion-focused (one emotion,
70/20/10 composition, three-test gate). Phase 8.3 makes it
outcome-driven by introducing a new hierarchy:

    business → business goal → audience → funnel stage → platform → image

The image is NOT the product. The business outcome is the product.
Every render must be optimised for the specific outcome the founder is
trying to create: a call, a booking, a sale, a store visit, a message,
a lead, or an upsell.

What that means in the prompt:

1. **Business goal leads the strategy.** Lead Generation renders
   "problem + solution"; Bookings render "experience"; Sales render
   "product outcome"; Brand Awareness renders "identity"; Retargeting
   renders "proof"; Upselling renders "premium outcome." This is named
   explicitly so the model picks a composition that earns the goal,
   not one that's merely pretty.

2. **Funnel stage shapes the persona.** Top-of-funnel viewers don't
   know the business yet — the prompt asks for curiosity / aspiration
   / social proof. Mid-funnel viewers know it — the prompt asks for
   trust / before-after / authority. Bottom-funnel viewers are ready
   to act — the prompt asks for urgency / clear offer / direct path
   to convert.

3. **Audience changes the scene.** Same restaurant, three different
   ads: families → parents + children enjoying a meal; young adults
   → friends + social atmosphere; professionals → lunch-meeting
   environment. The audience bucket is parsed from the profile and
   crossed with the business kind to pick a specific scene.

4. **Meta Ads Library mode.** The prompt now references the patterns
   that actually win on paid social — social proof, clear offer,
   customer outcome, emotional hook — and explicitly forbids the
   generic-stock-photo and generic-smiling-people patterns that lose.

5. **Five-test conversion gate.** The original three Phase 8.2 tests
   (scroll-stop, conversion, $5k-agency) are joined by the Phase 8.3
   OUTCOME TEST ("what business result is this image trying to
   create?") and FOUNDER TEST ("if this succeeds, what action will
   the customer take — call / book / buy / visit / message?"). If
   either is unclear, the prompt tells the model to re-plan.

Carry-forward from Phase 8.2 (none of this changes):

- Performance-first prologue (scroll-stop, campaign-ready, CLICKS /
  ENQUIRIES / BOOKINGS / LEADS / PURCHASES).
- Single primary emotion per render (curiosity / urgency / desire /
  trust / aspiration / FOMO), but now biased by funnel stage.
- 1-second WHAT / WHO / WHY contract.
- Industry blocks with sharp DOs/DON'Ts (no floating food, no
  bodybuilder photoshoots, no empty rooms, no call-centre framing).
- Platform persona (IG = scroll-stop, FB = trust-first, LinkedIn =
  authority-first).
- 70/20/10 composition rule.

Carry-forward from Phase 8.1 (none of this changes either):

- Ultra-realistic photography, not AI / 3D / CGI / cartoon.
- Sony A7R V / Canon EOS R5 vocabulary, EXIF-style framing.
- Subject-class branching (food / portrait / product / scene / screen).
- HUMAN RULES auto-fire when people are in frame.
- Separate structured `NEGATIVE_PROMPT` for providers that weight it.
- "No text in the image" — overlays happen in post.

Phase 8.2 (legacy section — still accurate):
============================================
Phase 8.1 made the output look like a real photograph instead of an AI
render. Phase 8.2 changes the WHY: we are no longer optimising for
"realism" or "agency aesthetic," we are optimising for

    "Would this OUTPERFORM typical small-business ads on Instagram
     and Facebook?"

The image still has to look real (the Phase 8.1 absolute rules — no
cartoon, no 3D, no CGI, anatomically correct hands — all stay in
force). But the success criterion is now CLICKS, ENQUIRIES, BOOKINGS,
LEADS, PURCHASES. Beauty without performance is failure.

What that means in the prompt:

1. **Performance framing leads.** The first thing the diffusion model
   reads is "scroll-stopping paid-ad creative engineered to convert",
   then the realism rules — not the other way around. Beauty serves
   the click; never the inverse.

2. **One emotion per image.** Every render carries ONE primary emotion
   from the curiosity / urgency / desire / trust / aspiration / FOMO
   set. We pick it deterministically from the brief's goal + mood +
   business kind and bake it into the prompt as a non-negotiable
   intent. Diffuse "mood keywords" alone weren't enough — the brief
   could say "warm, premium, calm" and produce a beautiful nothing.

3. **1-second test, not 3.** Phase 8.1 said the founder's three
   questions (WHAT / WHO / WHY) must land in three seconds. Phase 8.2
   tightens that to one second — that's the actual feed-scroll budget.

4. **Industry blocks shift from "real" to "performant."** Restaurant
   blocks now forbid the floating-food-on-white shot AND the fine-
   dining-magazine shot, and demand customers + atmosphere. Gym
   blocks forbid bodybuilder photoshoots AND fitness-magazine covers,
   and demand transformation / effort / coaching. Real-estate blocks
   forbid empty rooms only and demand walkthrough moments + client
   interaction. Service blocks demand visible trust + consultation +
   results.

5. **Social-media blocks carry persona.** Instagram = scroll-stop /
   bold hook / high contrast. Facebook = trust-first / result-first.
   LinkedIn = authority-first / professional-first.

6. **70/20/10 composition rule** named explicitly: 70% subject, 20%
   environment, 10% supporting context. Clutter is the enemy.

7. **Three-test conversion gate at the end.** The prompt now closes
   with the scroll-stop test, the spend-money test, and the $5k-
   agency test — the same three questions Phase 8.2 wants every
   render to pass before shipping.

Carry-forward from Phase 8.1 (none of this changes):

- Ultra-realistic photography, not AI / 3D / CGI / cartoon.
- Sony A7R V / Canon EOS R5 vocabulary, EXIF-style framing.
- Subject-class branching (food / portrait / product / scene / screen).
- HUMAN RULES auto-fire when people are in frame.
- Separate structured `NEGATIVE_PROMPT` for providers that weight it.
- "No text in the image" — overlays happen in post.
"""

from __future__ import annotations

from typing import Any

from aicmo.copy.banned_phrases import strip_overlay_text_instructions
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

# ---------------------------------------------------------------------
#  Pattern matchers — keywords pulled from `focal_subject` decide which
#  subject block fires. All matching is word-boundary (so "hand"
#  doesn't match "hand-thrown"); order doesn't matter.
# ---------------------------------------------------------------------


# Subject classes — pattern-matched against `focal_subject` via WORD-
# BOUNDARY regex. Order of check (highest specificity first):
#   SCREEN → PRODUCT → FOOD → PORTRAIT → SCENE
_FOOD_WORDS = (
    "espresso", "latte", "cappuccino", "flat white", "matcha", "smoothie",
    "cocktail", "wine", "beer", "whisky", "cocoa", "chocolate",
    "burger", "pizza", "salad", "pasta", "noodles", "ramen", "sushi",
    "sandwich", "wrap", "loaf", "bread", "pastry", "donut", "bagel",
    "croissant", "cake", "tart", "dessert", "soup", "steak", "fish",
    "seafood", "brunch", "menu",
    "pour", "plating", "brewing", "tasting",
)
_PORTRAIT_WORDS = (
    "person", "people", "founder", "team", "customer", "user", "model",
    "face", "portrait", "headshot", "owner", "athlete", "runner",
    "cyclist", "swimmer", "dancer", "musician", "designer", "artist",
    "doctor", "nurse", "teacher", "student",
    # Phase 8.1 — service / consulting human subjects.
    "consultant", "agent", "client", "trainer", "coach",
)
_PRODUCT_WORDS = (
    "product", "bottle", "can", "package", "packaging", "box", "device",
    "phone", "smartphone", "laptop", "watch", "shoe", "sneaker", "bag",
    "jar", "tube", "kit", "tool", "machine", "appliance", "gadget",
    "wearable", "earbuds", "headphones", "speaker", "camera", "console",
    "vehicle", "car", "bike", "case", "skincare", "cosmetic",
)
_SCENE_WORDS = (
    "interior", "exterior", "shop", "store", "storefront", "office",
    "studio", "workshop", "warehouse", "street", "city", "skyline",
    "room", "lobby", "venue", "stage", "set", "garden", "park",
    "landscape", "factory", "floor",
    # Phase 8.1 — real-estate / service environments.
    "property", "home", "house", "apartment", "kitchen", "facility",
    "gym",
)
_SCREEN_WORDS = (
    "screen", "ui", "dashboard", "interface", "app", "software", "saas",
    "browser", "window", "modal", "trackpad", "tablet", "monitor",
    "display",
)

# Subjects that imply a person is in the frame even when the focal
# subject is technically something else (e.g. a workout shot's focal
# subject is "barbell mid-lift" but a person is still rendered).
_PEOPLE_IMPLIED_WORDS = (
    "workout", "training", "session", "meeting", "consultation",
    "walkthrough", "demonstration", "lesson", "class", "service",
    "handover", "interaction", "conversation", "dining",
)


def _matches_any(text: str, words: tuple[str, ...]) -> bool:
    """Word-boundary match (so 'hand' doesn't match 'hand-thrown').
    Hyphens and slashes count as word boundaries.
    """
    import re

    for w in words:
        rx = r"(?<![a-z])" + re.escape(w) + r"(?![a-z])"
        if re.search(rx, text):
            return True
    return False


def _subject_class(focal: str) -> str:
    """Return a coarse subject class for `focal_subject` → drives which
    subject-specific realism block (if any) gets injected.

    Returns: "food" | "portrait" | "product" | "scene" | "screen" | ""
    Empty string means no specific class detected. Order:
    most-specific-first.
    """
    f = focal.lower()
    if _matches_any(f, _SCREEN_WORDS):
        return "screen"
    if _matches_any(f, _PRODUCT_WORDS):
        return "product"
    if _matches_any(f, _FOOD_WORDS):
        return "food"
    if _matches_any(f, _PORTRAIT_WORDS):
        return "portrait"
    if _matches_any(f, _SCENE_WORDS):
        return "scene"
    return ""


def _people_in_frame(focal: str, business_kind: str) -> bool:
    """Return True when the human-rules block should fire.

    Fires for explicit portrait subjects, for scene subjects that
    typically include people (workouts, consultations, dining), and
    for service / restaurant / gym / real-estate businesses where
    the human element is part of the brand promise even when the
    focal subject is the venue or product.
    """
    f = focal.lower()
    if _matches_any(f, _PORTRAIT_WORDS):
        return True
    if _matches_any(f, _PEOPLE_IMPLIED_WORDS):
        return True
    return business_kind in {"restaurant", "gym", "real_estate", "service_business"}


# ---------------------------------------------------------------------
#  Industry classifier — maps the founder's free-text industry into
#  the named business contexts the Phase 8.1 brief enumerates.
# ---------------------------------------------------------------------


_RESTAURANT_WORDS = (
    "restaurant", "cafe", "café", "coffee", "coffeeshop", "coffee shop",
    "bistro", "bar", "pub", "brewery", "winery", "food", "bakery",
    "kitchen", "diner", "eatery", "deli", "patisserie", "ice cream",
    "tea", "tea house", "juice", "smoothie", "catering",
)
_GYM_WORDS = (
    "gym", "fitness", "crossfit", "yoga", "pilates", "boxing",
    "kickboxing", "martial arts", "spin", "cycling studio",
    "personal training", "trainer", "strength", "wellness studio",
    "dance studio", "barre",
)
_REAL_ESTATE_WORDS = (
    "real estate", "realty", "realtor", "property", "properties",
    "homes", "broker", "brokerage", "mortgage", "leasing",
    "luxury homes",
)
_SERVICE_WORDS = (
    "consult", "consulting", "agency", "law", "legal", "lawyer",
    "attorney", "advisor", "advisory", "accountant", "accounting",
    "finance", "financial", "saas", "software", "marketing", "design",
    "creative", "freelance", "coaching", "coach", "tax", "insurance",
    "professional services",
)
_LOCAL_WORDS = (
    "shop", "store", "retail", "boutique", "salon", "barber",
    "florist", "local", "market", "grocery", "convenience",
    "hardware", "pet", "bookstore", "tailor", "spa",
)


def _business_kind(industry: str) -> str:
    """Map a free-text industry to one of the Phase 8.1 business
    contexts. Returns "" when no rule matches → no context block
    is injected (the prompt still works, just without the industry-
    specific cues).

    Order matters: restaurant / gym / real-estate are most-specific
    and beat the generic "service" / "local" buckets. We check those
    in priority order.

    Matching uses the same word-boundary regex helper as
    `_subject_class` — naive substring matching would mis-classify
    industries like "Aerospace" → "local_business" (because "spa" is
    a substring) or "Local barber" → "restaurant" (because "bar" is
    a substring of "barber"). The Phase 8.1 audit caught those.
    """
    i = (industry or "").lower()
    if _matches_any(i, _RESTAURANT_WORDS):
        return "restaurant"
    if _matches_any(i, _GYM_WORDS):
        return "gym"
    if _matches_any(i, _REAL_ESTATE_WORDS):
        return "real_estate"
    if _matches_any(i, _SERVICE_WORDS):
        return "service_business"
    if _matches_any(i, _LOCAL_WORDS):
        return "local_business"
    return ""


# ---------------------------------------------------------------------
#  Platform / aspect classifier — drives the Social Media block.
# ---------------------------------------------------------------------


def _normalize_aspect(aspect: str) -> str:
    a = (aspect or "").strip().lower().replace(" ", "")
    return {
        "1x1": "1:1", "square": "1:1",
        "4x5": "4:5", "portrait": "4:5",
        "9x16": "9:16", "story": "9:16", "vertical": "9:16",
        "16x9": "16:9", "landscape": "16:9", "wide": "16:9",
        "3x2": "3:2",
        "1.91:1": "1.91:1", "1.91x1": "1.91:1",
    }.get(a, a)


def _platform_kind(platform: str | None, aspect: str) -> str:
    """Classify the placement so we can attach a social-media
    optimisation block. Falls back to aspect-based inference when
    platform is unknown.

    Returns one of: "instagram_feed" | "instagram_reel" |
    "facebook_ad" | "linkedin" | "" (no specific block).
    """
    p = (platform or "").strip().lower()
    a = _normalize_aspect(aspect)
    if "instagram" in p or "ig" == p:
        if a in {"9:16", "4:5"}:
            return "instagram_reel"
        return "instagram_feed"
    if "facebook" in p or "fb" == p or "meta" in p:
        return "facebook_ad"
    if "linkedin" in p:
        return "linkedin"
    if "tiktok" in p or "short" in p or "reel" in p:
        return "instagram_reel"
    # No platform → infer from aspect.
    if a == "9:16":
        return "instagram_reel"
    if a == "1:1":
        return "instagram_feed"
    if a == "1.91:1":
        return "facebook_ad"
    return ""


# ---------------------------------------------------------------------
#  Static blocks — module-level so the prompt is deterministic and
#  fully diffable. Order in the final prompt mirrors the order here:
#  realism header → realism block → subject block → business context
#  → human rules → marketing rules → social media → anti-cliché →
#  reject → critical.
# ---------------------------------------------------------------------


_PERFORMANCE_HEADER = (
    "PERFORMANCE-FIRST PAID-AD CREATIVE — engineered to OUTPERFORM typical "
    "small-business ads on Instagram and Facebook. The mission is CLICKS, "
    "ENQUIRIES, BOOKINGS, LEADS, PURCHASES — not artistic quality. Every "
    "compositional choice serves the conversion goal. The image must be "
    "scroll-stopping, campaign-ready, and conversion-focused — modelled on "
    "the visual patterns that work in Meta Ads Library, top-performing "
    "Facebook ads, direct-response advertising, and modern DTC brands. "
    "Beauty without performance is failure. "
    "Execution standard: ULTRA-REALISTIC COMMERCIAL PHOTOGRAPHY captured on "
    "a Sony A7R V or Canon EOS R5 — never an AI render, never a cartoon, "
    "illustration, painting, watercolour, 3D render, or CGI composite, "
    "never a generic stock photograph."
)
# Back-compat alias — Phase 8.1 tests imported `_REALISM_HEADER` and a few
# downstream modules may reference it. Keeping the symbol prevents a
# silent break while pointing at the new performance-first content.
_REALISM_HEADER = _PERFORMANCE_HEADER


_PHOTOGRAPHIC_REALISM_BLOCK = """\
PHOTOGRAPHIC REALISM (commercial campaign standard — DSLR / mirrorless):
- Camera + lens: Sony A7R V or Canon EOS R5, 35mm or 50mm prime at f/2.0-f/4.0 (or 85mm f/2.8 for tight subjects). Sharp focus on the subject, naturally rolled-off background — NOT mushy creamy bokeh, NOT uniform soft blur.
- Lighting: physically correct, one dominant key light source — natural window daylight, golden-hour sun, a single practical lamp, or a softbox simulating one. Visible shadow direction, realistic shadow fall-off, ambient occlusion under every contact point. Slight contrast between lit and unlit sides of the subject.
- Skin + texture: realistic skin texture with visible pores, fine vellus hair, natural micro-imperfections. Surfaces show real material micro-texture — fabric weave, wood grain, ceramic glaze imperfections, fingerprints on glass, condensation on cold surfaces, dust suspended in light beams, scratches on metal, paint micro-crackle. NEVER airbrushed. NEVER plastic.
- Colour grading: real-world look — slight warm-cool split between highlight and shadow (the canonical advertising grade). Saturation is restrained and varies across the frame; the image is NEVER over-saturated or candy-coloured.
- Depth: three planes — a soft foreground anchor (out-of-focus prop, edge, hand, leaf), the sharp subject, a recognisable-but-defocused background. Never flatten everything onto one plane. Realistic depth of field.
- Composition: rule of thirds, single strong focal point, clear visual hierarchy. Modern commercial composition — the eye lands on the subject in <1 second.
- Reflections + shadows: physically correct given the camera position and key light direction. No mirror-perfect impossible reflections. No floating objects (every object has a clear contact shadow with the surface it sits on).
- Realism boosters — name these explicitly inside the rendered prompt: "professional commercial photography", "captured on Sony A7R V", "ultra realistic", "agency quality", "real-world lighting", "natural skin texture", "authentic environment", "photorealistic".
- Imperfection signals (these make an image READ as a real photo): subtle sensor grain in shadows, a wisp of motion smear on a moving subject, lived-in clutter (a folded napkin, a half-empty cup, a single dust mote in a light beam, papers stacked unevenly). Never perfectly still, never perfectly tidy.
"""


_HUMAN_RULES_BLOCK = """\
PEOPLE — must look real and relatable, not modelled or stylised:
- Natural, authentic, diverse, relatable — small-business owners, real customers, real employees in the actual setting. Mixed ages, body types, ethnicities.
- Mid-action: pouring, plating, lifting, demonstrating, talking, listening, walking through — NOT smiling at the camera with crossed arms, NOT a stiff hero pose.
- Faces: in-the-moment expressions, slight asymmetry, real micro-expressions. NO doll-like smoothness, NO glass-eye stare, NO mannequin geometry, NO fake or frozen smiles.
- Hands and fingers: anatomically correct — count the fingers, verify joint angles. NO extra fingers, NO fused digits, NO deformed or mutated hands. This is the single biggest tell of AI-generated portraits — guard it aggressively.
- Bodies: realistic proportions. NO fashion-model poses, NO influencer poses, NO unrealistic beauty, NO exaggerated expressions, NO airbrushed beauty.
- Clothing: real fabric drape with visible wrinkles, weave texture, slight asymmetry in collars and cuffs. Hair: individual strand definition, a few flyaways — never helmet-perfect.
"""


_MARKETING_RULES_BLOCK = """\
MARKETING CONTRACT — the image must communicate three things in UNDER ONE SECOND of a scroll:
1. WHAT is being offered — the product or service is unambiguous from the image alone, without any caption.
2. WHO it is for — the person in the frame OR the context around the product makes the audience obvious.
3. WHY they should care — the emotion, the moment, the result is visible in the scene.
The 1-second test is non-negotiable: a viewer scrolling at thumb-speed must catch all three without reading any text on the image.
"""


# Phase 8.2 — EMOTIONAL INTENT block. Every ad must carry exactly ONE
# of these emotions. We pick the emotion deterministically (see
# `_pick_emotion` below) and bake it into the prompt as a non-
# negotiable intent. Without this, "mood keywords" alone produce a
# beautiful nothing — the image looks nice but doesn't trigger an
# action.
_EMOTION_OPTIONS: tuple[str, ...] = (
    "curiosity",
    "urgency",
    "desire",
    "trust",
    "aspiration",
    "fomo",
)

_EMOTION_GUIDANCE: dict[str, str] = {
    "curiosity": (
        "Compose the frame around an UNRESOLVED QUESTION the viewer "
        "wants answered — a partial reveal, a mid-action moment, a "
        "result-but-not-yet-the-method. The eye lands and the brain "
        "asks 'wait, what?' within a quarter-second."
    ),
    "urgency": (
        "Compose for IMMEDIATE ACTION — a time-bound moment, a fleeting "
        "scene, a 'now or never' framing. Visual tension (motion blur on "
        "a passing element, a half-finished gesture, the last item on a "
        "shelf) makes 'later' feel like a loss."
    ),
    "desire": (
        "Compose for INSTANT WANT — the hero element is shown at peak "
        "appeal (steam rising off the food, lighting kissing the product, "
        "the result already in the customer's hands). The viewer should "
        "physically want to be in that frame within a second of seeing it."
    ),
    "trust": (
        "Compose for IMMEDIATE CREDIBILITY — real people doing real work, "
        "direct eye contact between humans, the actual venue / office / "
        "workshop, lived-in details that prove this is not staged. No "
        "polish, no stock-look — just a moment a customer would believe."
    ),
    "aspiration": (
        "Compose for the LIFE THE VIEWER WANTS — the result, the lifestyle, "
        "the version of themselves they're paying to become. The image is "
        "warm, inviting, and slightly idealised — but anchored in a "
        "plausible real-world setting, never fantasy."
    ),
    "fomo": (
        "Compose for FEAR-OF-MISSING-OUT — the moment is clearly happening "
        "to OTHER people right now, and the viewer is on the outside. A "
        "busy room, an over-the-shoulder POV looking in, a queue, a sold-"
        "out cue. The viewer should feel they need to be there."
    ),
}


_INDUSTRY_DEFAULT_EMOTION: dict[str, str] = {
    "restaurant": "desire",
    "gym": "aspiration",
    "real_estate": "aspiration",
    "service_business": "trust",
    "local_business": "trust",
}


def _pick_emotion(
    *,
    brief: dict[str, Any],
    business_kind: str,
    funnel_stage: str | None = None,
) -> str:
    """Deterministically pick the single primary emotion this ad must
    trigger. Order of precedence:

      1. `brief["emotional_intent"]` if explicitly set by the upstream
         brief LLM and it matches one of the six allowed options.
      2. The brief's `goal` / `mood_keywords` parsed for emotion words
         (e.g. "limited-time" → urgency, "trust" → trust, etc.).
      3. **Phase 8.3** — funnel-stage preference (TOF → curiosity /
         aspiration; MOF → trust / aspiration; BOF → urgency / desire
         / FOMO). Only consulted when steps 1 and 2 found nothing.
      4. The industry default (restaurant → desire, gym → aspiration,
         service → trust, etc.).
      5. Final fallback: "curiosity" — the safest scroll-stop default.

    Exported so tests can lock the policy in.
    """
    explicit = (brief.get("emotional_intent") or "").strip().lower()
    if explicit in _EMOTION_OPTIONS:
        return explicit

    haystack = " ".join(
        [
            str(brief.get("goal") or ""),
            str(brief.get("conversion_rationale") or ""),
            " ".join(brief.get("mood_keywords") or []),
        ]
    ).lower()
    if any(k in haystack for k in ("limited", "ending", "deadline", "today only", "ends ", "last chance", "while supplies")):
        return "urgency"
    if any(k in haystack for k in ("fomo", "miss out", "everyone is", "joined", "sold out")):
        return "fomo"
    if any(k in haystack for k in ("trust", "credibility", "proof", "case study", "testimonial", "results delivered")):
        return "trust"
    if any(k in haystack for k in ("transformation", "aspiration", "dream", "lifestyle", "be the")):
        return "aspiration"
    if any(k in haystack for k in ("curiosity", "reveal", "secret", "did you know", "behind the")):
        return "curiosity"
    if any(k in haystack for k in ("desire", "crave", "want", "tasty", "delicious", "irresistible")):
        return "desire"

    # Phase 8.3 — funnel-stage bias. When the brief is silent on
    # emotion, the funnel stage tells us what emotion FAMILY the
    # viewer is most receptive to.
    if funnel_stage in _FUNNEL_EMOTION_PREFERENCE:
        preferences = _FUNNEL_EMOTION_PREFERENCE[funnel_stage]
        # Cross-check with the industry default — if the industry's
        # natural emotion is in the funnel's preferred family, use it.
        industry_default = _INDUSTRY_DEFAULT_EMOTION.get(business_kind)
        if industry_default and industry_default in preferences:
            return industry_default
        # Otherwise pick the first funnel-preferred emotion.
        return preferences[0]

    if business_kind in _INDUSTRY_DEFAULT_EMOTION:
        return _INDUSTRY_DEFAULT_EMOTION[business_kind]
    return "curiosity"


def _emotion_block(emotion: str) -> str:
    """Render the EMOTIONAL INTENT block for one of the six allowed
    emotions. Caller is expected to pass a value that matches an entry
    in `_EMOTION_OPTIONS`; if not, we degrade to "curiosity".
    """
    e = emotion if emotion in _EMOTION_OPTIONS else "curiosity"
    return (
        f"EMOTIONAL INTENT — this image must trigger exactly ONE emotion: {e.upper()}.\n"
        f"{_EMOTION_GUIDANCE[e]}\n"
        "Never split the frame across two emotions — that's how images become 'beautiful but unmemorable'. "
        "Pick the emotion, design the entire composition to deliver it."
    )


# Phase 8.2 — 70/20/10 composition rule. Forbids clutter and forces a
# single dominant subject. Named explicitly because diffusion models
# happily fill every pixel when given the chance.
_COMPOSITION_RULE_BLOCK = """\
COMPOSITION RULE — 70 / 20 / 10:
- ~70% of the visual weight is the SUBJECT (the product, the person, the moment that earns the click).
- ~20% is the ENVIRONMENT that makes the subject's context obvious (the cafe, the gym floor, the office, the home).
- ~10% is supporting CONTEXT — a single secondary element that reinforces the story (a customer in the background, a tool in use, a result on a screen).
- Avoid clutter. Avoid multiple focal points. Avoid background-noise crowding the subject. One dominant subject wins the scroll; three small subjects lose it.
"""


# Phase 8.2 + 8.3 + 8.4 — the six conversion gates. The Phase 8.2 trio
# (scroll-stop, conversion, $5k-agency) is joined by the Phase 8.3
# OUTCOME TEST + FOUNDER TEST, and by the Phase 8.4 CREATIVE UNIQUENESS
# TEST that enforces ad-fatigue protection across consecutive renders.
# Soft constraint — diffusion models can't truly self-evaluate — but it
# biases the sampler towards outcome-shaped, varied composition.
_CONVERSION_GATE_BLOCK = """\
CONVERSION GATE — every image must pass ALL SIX tests:
1. SCROLL-STOP TEST: Show the image to a stranger for ONE second. Ask "what is happening?" If the answer is unclear in one second, reject the composition. The frame must have a single strong focal point, a clear emotional hook, and high contrast against a feed that is mostly photos of food, faces, and screenshots.
2. CONVERSION TEST: "Would a small-business owner spend money promoting this creative?" The offer / product / service must be obvious AND look credible enough to spend ad budget on.
3. AGENCY-QUALITY TEST: "Does this look like a creative produced by a professional marketing agency charging $5,000+ per campaign?" The execution must be indistinguishable from a paid-for shoot — no AI tells, no stock-photo feel, no design-showcase distraction.
4. OUTCOME TEST: "What business result is this image trying to create?" The answer must be unambiguous from the frame alone — a lead, a phone call, a WhatsApp message, a booking, a store visit, a product sale, brand recall, a retarget click, or an upsell. If the answer is unclear, re-plan the composition.
5. FOUNDER TEST: "If this image succeeds, what action will the customer take?" The answer must be one of: CALL, BOOK, BUY, VISIT, or MESSAGE. If no specific action is obvious, re-plan the composition.
6. CREATIVE UNIQUENESS TEST: Compare the planned composition against the recent concept-family chain in the ROTATION CONTEXT above. If concept overlap with any of the last 3 renders is more than 60% (same scene type, same angle, same energy, same hook family) — regenerate. A founder must be able to ship 20 ads in a row without the feed feeling repetitive.
If the composition you're about to produce would fail any one of these — re-plan it before rendering.
"""


# ---------------------------------------------------------------------
#  Phase 8.3 — Outcome-driven creative engine
#  --------------------------------------------------------------------
#  The hierarchy is: business → BUSINESS GOAL → AUDIENCE → FUNNEL STAGE
#  → platform → image. The renderer now classifies the goal, the
#  funnel stage and the audience bucket, and surfaces a goal-specific
#  visual strategy + audience-shaped scene + funnel-stage persona in
#  the prompt.
# ---------------------------------------------------------------------


# The 9 canonical goals from the Phase 8.3 brief. The keys are the
# canonical slugs we use internally; the human-facing label is the
# value we surface to the model.
_GOAL_LABELS: dict[str, str] = {
    "lead_generation": "Lead Generation",
    "phone_calls": "Phone Calls",
    "whatsapp_messages": "WhatsApp Messages",
    "bookings": "Bookings",
    "store_visits": "Store Visits",
    "product_sales": "Product Sales",
    "brand_awareness": "Brand Awareness",
    "retargeting": "Retargeting",
    "upselling": "Upselling Existing Customers",
}

_GOAL_OPTIONS: tuple[str, ...] = tuple(_GOAL_LABELS.keys())


# Per Phase 8.3, goal selects a VISUAL STRATEGY. This is the single
# most outcome-shaping line in the prompt — it tells the model "show
# X" rather than "make it look nice."
_VISUAL_STRATEGY: dict[str, str] = {
    "lead_generation": (
        "Show PROBLEM + SOLUTION. The frame contains a visible pain point "
        "OR an unmet need — then a clear visual cue of how this business "
        "solves it. The viewer should immediately think: 'that's me — "
        "and that fixes it.'"
    ),
    "phone_calls": (
        "Show DIRECT CONTACT + URGENCY. A human, mid-call or about to be "
        "reached — phone in hand, contact moment captured, immediacy in "
        "the body language. The viewer should feel that picking up the "
        "phone is the obvious next step."
    ),
    "whatsapp_messages": (
        "Show FAST RESPONSE. A real conversation in motion — a phone "
        "screen mid-message, a customer being helped in real time, a "
        "human responding within seconds. Communicate 'we reply now', "
        "without ever rendering readable text."
    ),
    "bookings": (
        "Show EXPERIENCE. Don't show the venue empty or the product on "
        "a shelf — show the experience the customer is paying to have. "
        "The moment they came for, captured at peak appeal. The viewer "
        "should want to be in that frame this week."
    ),
    "store_visits": (
        "Show the IN-STORE MOMENT + a clear sense of place. Frame the "
        "venue from a customer-eye-view — entrance, counter, atmosphere — "
        "with a real customer mid-visit. The viewer should picture "
        "walking in themselves."
    ),
    "product_sales": (
        "Show the PRODUCT OUTCOME in use, not the product on a plinth. "
        "The customer enjoying the result, the meal being eaten, the "
        "garment being worn, the gadget mid-action. Frame the value the "
        "customer gets, not the SKU."
    ),
    "brand_awareness": (
        "Show IDENTITY. The hero element captures something only THIS "
        "brand could produce — a signature dish, a signature space, a "
        "signature gesture, the founder's craft. The viewer should "
        "remember the brand, not the offer."
    ),
    "retargeting": (
        "Show PROOF. A real customer enjoying the result, a real before/"
        "after, a real testimonial moment, a real client outcome. The "
        "viewer has already seen us once — this frame is what closes "
        "the gap from 'maybe' to 'yes'."
    ),
    "upselling": (
        "Show PREMIUM OUTCOME. The next tier of the experience — the "
        "upgrade in use, the deluxe version being enjoyed, the result "
        "an existing customer doesn't yet have. The viewer should "
        "feel like they're missing out on the better version."
    ),
}


# Goal aliases — what the visuals-brief LLM, an ad-objective dropdown,
# or a founder might actually write. Mapped to the canonical slug.
# Order: longest / most-specific patterns first so e.g. "phone calls"
# beats "phone" alone if both appear.
_GOAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("whatsapp", "whatsapp_messages"),
    ("dm us", "whatsapp_messages"),
    ("message us", "whatsapp_messages"),
    ("text us", "whatsapp_messages"),
    ("phone call", "phone_calls"),
    ("call us", "phone_calls"),
    ("call now", "phone_calls"),
    ("ring us", "phone_calls"),
    ("get a call", "phone_calls"),
    ("walk-in", "store_visits"),
    ("walk in", "store_visits"),
    ("foot traffic", "store_visits"),
    ("visit our", "store_visits"),
    ("come to our", "store_visits"),
    ("store visit", "store_visits"),
    ("in-store", "store_visits"),
    ("retarget", "retargeting"),
    ("re-target", "retargeting"),
    ("remarket", "retargeting"),
    ("re-engage", "retargeting"),
    ("warm audience", "retargeting"),
    ("upsell", "upselling"),
    ("up-sell", "upselling"),
    ("upgrade existing", "upselling"),
    ("existing customer", "upselling"),
    ("cross-sell", "upselling"),
    ("brand awareness", "brand_awareness"),
    ("awareness", "brand_awareness"),
    ("brand recall", "brand_awareness"),
    ("introduce our", "brand_awareness"),
    ("launch our", "brand_awareness"),
    ("booking", "bookings"),
    ("reservation", "bookings"),
    ("book a table", "bookings"),
    ("book an appointment", "bookings"),
    ("schedule", "bookings"),
    ("appointment", "bookings"),
    ("sale", "product_sales"),
    ("sales", "product_sales"),
    ("purchase", "product_sales"),
    ("checkout", "product_sales"),
    ("buy now", "product_sales"),
    ("order now", "product_sales"),
    ("shop now", "product_sales"),
    ("conversion", "product_sales"),
    ("lead generation", "lead_generation"),
    ("generate leads", "lead_generation"),
    ("lead form", "lead_generation"),
    ("enquir", "lead_generation"),
    ("inquir", "lead_generation"),
    ("get quotes", "lead_generation"),
    ("free consult", "lead_generation"),
    ("sign up", "lead_generation"),
    ("signup", "lead_generation"),
    ("newsletter", "lead_generation"),
)


# Industry → default goal when the brief gives us nothing else to go on.
_INDUSTRY_DEFAULT_GOAL: dict[str, str] = {
    "restaurant": "bookings",
    "gym": "lead_generation",
    "real_estate": "lead_generation",
    "service_business": "lead_generation",
    "local_business": "store_visits",
}


def _pick_goal(*, brief: dict[str, Any], business_kind: str) -> str:
    """Choose one of the 9 canonical business goals for this render.

    Precedence:
      1. `brief["business_goal"]` if it matches a known slug.
      2. Substring scan of the brief's `goal` / `objective` /
         `conversion_rationale` / `cta_copy` against `_GOAL_PATTERNS`.
      3. Industry default (restaurant → bookings, gym → lead gen, etc.).
      4. Final fallback: `lead_generation` — the safest default for a
         small-business paid-social ad.

    Exported so tests can pin the policy.
    """
    explicit = (brief.get("business_goal") or "").strip().lower().replace(" ", "_")
    if explicit in _GOAL_OPTIONS:
        return explicit

    haystack = " ".join(
        [
            str(brief.get("goal") or ""),
            str(brief.get("objective") or ""),
            str(brief.get("conversion_rationale") or ""),
            str(brief.get("cta_copy") or ""),
        ]
    ).lower()
    for needle, slug in _GOAL_PATTERNS:
        if needle in haystack:
            return slug

    if business_kind in _INDUSTRY_DEFAULT_GOAL:
        return _INDUSTRY_DEFAULT_GOAL[business_kind]
    return "lead_generation"


def _goal_block(goal: str) -> str:
    """Render the BUSINESS GOAL + VISUAL STRATEGY block — the single
    most outcome-shaping line in the prompt.
    """
    g = goal if goal in _GOAL_OPTIONS else "lead_generation"
    return (
        f"BUSINESS GOAL — this creative must drive: {_GOAL_LABELS[g]}.\n"
        f"VISUAL STRATEGY: {_VISUAL_STRATEGY[g]}\n"
        "The image is NOT the product. The business outcome is the product. Compose for the outcome — not for the artwork."
    )


# Funnel-stage classifier. The Phase 8.3 brief defines three stages
# and a "user state" + "goal" + "emotion family" for each.
_FUNNEL_STAGES = ("top", "middle", "bottom")

# Goal → default funnel stage. Top-of-funnel = the viewer doesn't know
# the business yet; bottom-of-funnel = the viewer is ready to act.
_GOAL_FUNNEL_DEFAULT: dict[str, str] = {
    "brand_awareness": "top",
    "lead_generation": "middle",
    "retargeting": "middle",
    "bookings": "bottom",
    "phone_calls": "bottom",
    "whatsapp_messages": "bottom",
    "store_visits": "bottom",
    "product_sales": "bottom",
    "upselling": "bottom",
}

_FUNNEL_BLOCKS: dict[str, str] = {
    "top": (
        "FUNNEL STAGE — TOP OF FUNNEL (viewer does not yet know the business).\n"
        "Goal: ATTENTION. The frame must earn a stranger's first thought-stop. "
        "Lean on CURIOSITY (an unresolved question), ASPIRATION (the life the "
        "viewer wants), or SOCIAL PROOF (other people already loving it). "
        "Do not assume the viewer knows your brand, your offer, or your category."
    ),
    "middle": (
        "FUNNEL STAGE — MIDDLE OF FUNNEL (viewer knows the business, weighing it).\n"
        "Goal: TRUST. The viewer has met us before and is asking 'is this real, "
        "and is it for me?' Lean on BEFORE/AFTER moments, CUSTOMER SUCCESS, or "
        "AUTHORITY signals (the founder at work, the venue in action, a credible "
        "result on display). Close the doubt gap."
    ),
    "bottom": (
        "FUNNEL STAGE — BOTTOM OF FUNNEL (viewer is ready to act).\n"
        "Goal: CONVERSION. The viewer knows us, trusts us, and is one nudge "
        "away. The frame must surface a clear offer, a clear next action, and "
        "a credible promise — BOOKING / PURCHASE / INQUIRY moment captured. "
        "Make the next step the path of least resistance."
    ),
}


def _pick_funnel_stage(*, brief: dict[str, Any], goal: str) -> str:
    """Pick the funnel stage. Precedence:
      1. Explicit `brief["funnel_stage"]` field if it's tof/mof/bof or
         top/middle/bottom.
      2. Goal → stage mapping.
      3. Default to "middle" (the safest default for a small-business
         creative that's not explicitly brand-launch or hard-close).
    """
    explicit = (brief.get("funnel_stage") or "").strip().lower()
    aliases = {
        "top": "top",
        "tof": "top",
        "top-of-funnel": "top",
        "awareness": "top",
        "middle": "middle",
        "mof": "middle",
        "mid": "middle",
        "consideration": "middle",
        "bottom": "bottom",
        "bof": "bottom",
        "bottom-of-funnel": "bottom",
        "conversion": "bottom",
        "purchase": "bottom",
        "decision": "bottom",
    }
    if explicit in aliases:
        return aliases[explicit]
    if goal in _GOAL_FUNNEL_DEFAULT:
        return _GOAL_FUNNEL_DEFAULT[goal]
    return "middle"


def _funnel_block(stage: str) -> str:
    s = stage if stage in _FUNNEL_STAGES else "middle"
    return _FUNNEL_BLOCKS[s]


# Audience-bucket classifier. Diffusion models do much better with a
# clear "show a couple in their 30s" than with a paragraph of
# demographic prose — so we condense the founder's `target_audience`
# into ONE bucket and then look up a business-specific scene hint.
_AUDIENCE_OPTIONS: tuple[str, ...] = (
    "families",
    "young_adults",
    "professionals",
    "couples",
    "seniors",
    "students",
    "general",
)

_AUDIENCE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("families", "families"),
    ("family", "families"),
    ("parents", "families"),
    ("kids", "families"),
    ("children", "families"),
    ("moms", "families"),
    ("dads", "families"),
    ("date night", "couples"),
    ("couples", "couples"),
    ("partners", "couples"),
    ("newlywed", "couples"),
    ("seniors", "seniors"),
    ("retirees", "seniors"),
    ("elderly", "seniors"),
    ("60+", "seniors"),
    ("65+", "seniors"),
    ("students", "students"),
    ("college", "students"),
    ("university", "students"),
    ("teens", "students"),
    ("professional", "professionals"),
    ("executives", "professionals"),
    ("entrepreneur", "professionals"),
    ("founders", "professionals"),
    ("b2b", "professionals"),
    ("corporate", "professionals"),
    ("remote workers", "professionals"),
    ("freelancer", "professionals"),
    ("young adult", "young_adults"),
    ("millennial", "young_adults"),
    ("gen z", "young_adults"),
    ("18-24", "young_adults"),
    ("18-29", "young_adults"),
    ("25-34", "young_adults"),
    ("aged 25", "young_adults"),
    ("aged 18", "young_adults"),
    ("twenty-something", "young_adults"),
    ("twentysomething", "young_adults"),
)


def _pick_audience(profile: BusinessProfileResponse) -> str:
    """Condense the founder's free-text `target_audience` into one of
    seven canonical buckets so the renderer can pick a scene that
    actually matches the people in the frame.

    Falls back to `general` when no pattern matches.
    """
    haystack = (profile.target_audience or "").lower()
    for needle, bucket in _AUDIENCE_PATTERNS:
        if needle in haystack:
            return bucket
    return "general"


# Audience-shaped scene hints. Cross-product of `business_kind` x
# `audience_bucket` — the Phase 8.3 brief's restaurant examples
# (families → parents+kids, young adults → friends+social, pros →
# lunch meeting) are the canonical template; the rest are extrapolated
# in the same shape.
_AUDIENCE_SCENE_HINTS: dict[str, dict[str, str]] = {
    "restaurant": {
        "families": "Parents and children sharing a meal at the same table, kids genuinely engaged with their food, parents at ease — the kind of weeknight scene a family wants to recreate.",
        "young_adults": "A group of friends mid-laugh around a shared table, drinks being passed, food being shared — peak social-atmosphere energy.",
        "professionals": "A working lunch in progress — two professionals over a quick meal, laptop closed, conversation in motion. Clean, daytime light.",
        "couples": "A two-top date-night scene — soft candle light, a single shared dish, leaning-in body language, glasses raised.",
        "seniors": "A relaxed midday meal with older guests being served warmly by staff, daylight, unhurried pace.",
        "students": "An affordable, casual shared-table moment — a small group of students, takeaway-style plates, laptops nearby.",
    },
    "gym": {
        "families": "A family fitness moment — a parent and child stretching together, or a parent training while the kid does kids-class in the background plane.",
        "young_adults": "A small-group HIIT or class moment — peers pushing each other through a final round, sweat sheen, real effort.",
        "professionals": "A focused before-work session — a single member mid-set, the gym half-empty, a coach in the background. Clean morning light.",
        "couples": "Two partners training together — spotting, high-five on a finished set, shared progress moment.",
        "seniors": "A senior member working with a coach on a low-impact movement — supportive, careful, dignified. Never patronising.",
        "students": "A student-affordable scene — campus or budget-gym energy, a small group warming up together, gear that feels real and used.",
    },
    "real_estate": {
        "families": "A family walking through a home for the first time — kids exploring a bedroom, parents in the kitchen with the agent. Daylight, real reactions.",
        "young_adults": "First-time-buyer energy — a young person standing in the doorway of a place they can finally afford, agent handing over keys.",
        "professionals": "A high-end property viewing — a professional client with the agent in a premium kitchen / view space, discussion in motion.",
        "couples": "A couple touring together — one of them turning to the other mid-room, the moment the place becomes 'theirs'.",
        "seniors": "An empty-nester downsize moment — a calm walkthrough of a single-story or low-maintenance home with the agent.",
        "students": "A rental-share viewing — a small group walking a flat together, agent giving the tour.",
    },
    "service_business": {
        "families": "A family-facing service moment — advisor sitting with a parent at a kitchen table, real paperwork in motion (no readable text).",
        "young_adults": "A modern advisory moment — a young client on a sofa with a laptop open, the consultant beside them mid-explanation, screen showing a clear visual chart (no readable text).",
        "professionals": "A boardroom-table consultation — the advisor mid-presentation, the client leaning in, a screen showing a chart-up trend (no readable text).",
        "couples": "A couple consulting an advisor together — both clients side-by-side, advisor across the table, document in use.",
        "seniors": "A senior client with a trusted advisor — calm, careful explanation, advisor pointing to a clear visual (no readable text).",
        "students": "A first-time-client moment — a young client in a casual consult, advisor making it feel approachable.",
    },
    "local_business": {
        "families": "A parent and child picking out an item together — the kid is the one choosing, the parent watching. Daylight, real shop atmosphere.",
        "young_adults": "Two friends browsing together — one holding an item up to the other, real moment of recommendation.",
        "professionals": "A weekday lunchtime drop-in — a professional grabbing something quick, owner handing it over with a brief exchange.",
        "couples": "A couple picking something together — small moment of agreement, owner ringing it up in the background.",
        "seniors": "An older regular being served by the owner — first-name energy, real familiarity, never patronising.",
        "students": "A student-friendly affordable purchase — a small group sharing the moment, casual energy, owner involved.",
    },
}


def _audience_block(*, business_kind: str, audience: str) -> str:
    """Render the AUDIENCE block — a short, very specific scene hint
    derived from the cross-product of business kind and audience
    bucket. Falls back gracefully:

      - If we have a scene hint, surface it.
      - Otherwise, name the audience bucket so the model at least
        gets the right people in the frame.
    """
    if business_kind in _AUDIENCE_SCENE_HINTS and audience in _AUDIENCE_SCENE_HINTS[business_kind]:
        hint = _AUDIENCE_SCENE_HINTS[business_kind][audience]
        return (
            f"AUDIENCE — this ad is for: {audience.replace('_', ' ')}.\n"
            f"Scene direction: {hint}\n"
            "Cast the people in the frame to match this audience exactly — wrong "
            "demographic in the frame is the single fastest way to lose the click."
        )
    if audience != "general":
        return (
            f"AUDIENCE — this ad is for: {audience.replace('_', ' ')}.\n"
            "Cast the people in the frame to match this audience exactly — wrong "
            "demographic in the frame is the single fastest way to lose the click."
        )
    return (
        "AUDIENCE — broad / general consumer.\n"
        "Cast a realistic, relatable person who matches the founder's actual "
        "customer base, not a model. The wrong demographic in the frame is the "
        "single fastest way to lose the click."
    )


# Phase 8.3 — Meta Ads Library mode. Names the patterns that actually
# win on paid social, and explicitly forbids the patterns that lose.
_META_ADS_LIBRARY_BLOCK = """\
META ADS LIBRARY MODE — mimic patterns commonly found in winning Meta ads:
- SOCIAL PROOF — other real people visibly enjoying the offer, a queue at the counter, a class full of members, a busy table in the background.
- CLEAR OFFER — the WHAT is unambiguous from the frame (the dish, the class, the property, the service in action), so the headline overlay can lean on the WHY.
- CUSTOMER OUTCOME — the result the customer is paying for, captured in the frame (the meal eaten, the body changed, the keys received, the problem solved).
- EMOTIONAL HOOK — one strong emotion landing on the viewer's first glance (curiosity / urgency / desire / trust / aspiration / FOMO), never "merely beautiful".
NEVER — patterns that lose on paid social:
- Generic stock photography (the "happy diverse team at a sunlit table" cliche).
- Generic smiling people staring straight at the camera with crossed arms.
- Product on a plain backdrop with no human, no context, no outcome.
- Beautiful empty venues with no people, no story, no offer.
"""


# Phase 8.3 — emotion bias by funnel stage. Top-of-funnel viewers
# don't know us yet → curiosity / aspiration / social-proof family
# of emotions. Middle-of-funnel viewers are weighing us → trust.
# Bottom-of-funnel viewers are ready to act → urgency / desire / FOMO.
_FUNNEL_EMOTION_PREFERENCE: dict[str, tuple[str, ...]] = {
    "top": ("curiosity", "aspiration"),
    "middle": ("trust", "aspiration"),
    "bottom": ("urgency", "desire", "fomo"),
}


# ---------------------------------------------------------------------
#  Phase 8.4 — Creative Diversity Engine
#  --------------------------------------------------------------------
#  Twelve concept families, one per render. The family is picked at
#  render time (deterministic but rotation-aware) and named in both
#  the human-facing prompt and a machine-parseable marker line so
#  `render.py` can regex it back out of prior prompts to enforce
#  ad-fatigue protection.
# ---------------------------------------------------------------------


# The 12 concept families from the Phase 8.4 brief. Order here is also
# the deterministic-tiebreak preference order when nothing else
# discriminates two equally-good candidates.
_CONCEPT_FAMILY_OPTIONS: tuple[str, ...] = (
    "customer_transformation",
    "before_after",
    "founder_story",
    "customer_testimonial",
    "social_proof",
    "product_demonstration",
    "behind_the_scenes",
    "authority_positioning",
    "problem_awareness",
    "lifestyle_aspiration",
    "community",
    "offer_driven",
)

_CONCEPT_FAMILY_LABELS: dict[str, str] = {
    "customer_transformation": "Customer Transformation",
    "before_after": "Before vs After",
    "founder_story": "Founder Story",
    "customer_testimonial": "Customer Testimonial",
    "social_proof": "Social Proof",
    "product_demonstration": "Product Demonstration",
    "behind_the_scenes": "Behind The Scenes",
    "authority_positioning": "Authority Positioning",
    "problem_awareness": "Problem Awareness",
    "lifestyle_aspiration": "Lifestyle Aspiration",
    "community": "Community",
    "offer_driven": "Offer Driven",
}


# One-line scroll-stop hook per family. These are the angle the
# composition should anchor to — the diffusion model can compose
# AROUND the hook rather than around generic "premium" energy.
_CONCEPT_FAMILY_HOOKS: dict[str, str] = {
    "customer_transformation": "See what changed for them.",
    "before_after": "Look what changed.",
    "founder_story": "Meet the person behind the work.",
    "customer_testimonial": "Hear it from a real customer.",
    "social_proof": "Everyone is choosing this.",
    "product_demonstration": "Watch it work.",
    "behind_the_scenes": "Here's what you don't normally see.",
    "authority_positioning": "Experts recommend this.",
    "problem_awareness": "Still struggling with this?",
    "lifestyle_aspiration": "Imagine this is your life.",
    "community": "Find your people here.",
    "offer_driven": "Don't miss this.",
}


# Scene direction per family. Tells the model WHAT to compose so the
# concept reads from the frame in under a second.
_CONCEPT_FAMILY_SCENE_DIRECTION: dict[str, str] = {
    "customer_transformation": (
        "Frame a real customer mid-transformation — visibly different "
        "from where they started, captured in the moment of the new "
        "result becoming theirs. The viewer should think 'that could "
        "be me in 6 weeks'."
    ),
    "before_after": (
        "Compose a side-by-side OR a single-frame moment that implies "
        "both states (the before condition still legible in the frame, "
        "the after result dominant). The change is the subject — not "
        "the venue, not the product, not the brand."
    ),
    "founder_story": (
        "Frame the founder mid-craft — hands-on, mid-action, in the "
        "actual venue. Eye contact with the camera is OK but the moment "
        "must look candid, not posed. The viewer should think 'this "
        "person built this themselves'."
    ),
    "customer_testimonial": (
        "Frame a real customer mid-quote — caught in conversation, "
        "head turned slightly, hands gesturing, the venue or result "
        "visible behind them. Never a stiff portrait staring at the "
        "camera. The viewer should think 'I trust her'."
    ),
    "social_proof": (
        "Frame the venue / class / counter / dining room at peak load "
        "— other real customers visibly engaged, queue forming, every "
        "seat taken. The crowd is the subject. The viewer should "
        "think 'everyone is already here'."
    ),
    "product_demonstration": (
        "Frame the product / service / dish / workout being USED in "
        "real time — mid-action, mid-step, mid-bite, mid-rep. Show "
        "the value the customer GETS, not the SKU on a shelf. The "
        "viewer should think 'I want to try that'."
    ),
    "behind_the_scenes": (
        "Frame an unguarded moment most customers never see — the "
        "morning prep, the workshop bench, the founder closing up, "
        "the team rehearsing the recipe. The viewer should think "
        "'now I see why this is different'."
    ),
    "authority_positioning": (
        "Frame the expert mid-explanation — coach correcting form, "
        "chef plating a signature dish, agent walking a client through "
        "a contract, advisor pointing to a clear visual. The viewer "
        "should think 'they know what they're doing'."
    ),
    "problem_awareness": (
        "Frame the PROBLEM the viewer recognises in themselves — the "
        "frustrated moment, the unhealthy habit, the empty room, the "
        "stuck position. The solution is implied by the brand, not "
        "shown. The viewer should think 'that's me — and I'm tired "
        "of it'."
    ),
    "lifestyle_aspiration": (
        "Frame the life the customer is paying to live — the easy "
        "morning, the celebrated meal, the new home, the confident "
        "body, the recovered weekend. Anchor it in a plausible "
        "real-world setting, never fantasy. The viewer should think "
        "'I want THAT life'."
    ),
    "community": (
        "Frame multiple customers together — the class mid-rep, the "
        "regulars at the counter, the shared table, the open-house "
        "crowd. Belonging is the subject. The viewer should think "
        "'these are my people'."
    ),
    "offer_driven": (
        "Frame the OFFER as the hero — the dish that's on offer this "
        "week, the trial pass, the booking moment captured mid-action, "
        "the limited-quantity signal (last seats, last properties, "
        "last slots). The viewer should think 'I need to act now'."
    ),
}


# Goal → ranked preferred concept families. The picker walks this
# list in order, skipping anything in `recent_concept_families`, and
# only falls back to the wider 12-family pool if every preferred
# family was recently used. Tuned to the Phase 8.4 examples:
#   Restaurant Bookings → Transformation / Social Proof / Authority / Lifestyle
#   Gym Leads          → Transformation / Community / Authority / Problem
#   Real-estate Calls  → Lifestyle / Authority / Social Proof / Aspiration
_GOAL_CONCEPT_PREFERENCE: dict[str, tuple[str, ...]] = {
    "lead_generation": (
        "problem_awareness",
        "customer_testimonial",
        "authority_positioning",
        "before_after",
        "founder_story",
        "social_proof",
    ),
    "phone_calls": (
        "authority_positioning",
        "social_proof",
        "problem_awareness",
        "customer_testimonial",
        "offer_driven",
        "lifestyle_aspiration",
    ),
    "whatsapp_messages": (
        "behind_the_scenes",
        "founder_story",
        "customer_testimonial",
        "authority_positioning",
        "social_proof",
        "problem_awareness",
    ),
    "bookings": (
        "lifestyle_aspiration",
        "social_proof",
        "customer_transformation",
        "authority_positioning",
        "offer_driven",
        "community",
    ),
    "store_visits": (
        "community",
        "social_proof",
        "lifestyle_aspiration",
        "offer_driven",
        "founder_story",
        "behind_the_scenes",
    ),
    "product_sales": (
        "product_demonstration",
        "before_after",
        "customer_testimonial",
        "offer_driven",
        "lifestyle_aspiration",
        "social_proof",
    ),
    "brand_awareness": (
        "founder_story",
        "behind_the_scenes",
        "authority_positioning",
        "lifestyle_aspiration",
        "community",
        "customer_transformation",
    ),
    "retargeting": (
        "customer_testimonial",
        "before_after",
        "social_proof",
        "offer_driven",
        "customer_transformation",
        "authority_positioning",
    ),
    "upselling": (
        "customer_transformation",
        "authority_positioning",
        "lifestyle_aspiration",
        "product_demonstration",
        "founder_story",
        "offer_driven",
    ),
}


def _normalise_recent(recent: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Filter the caller's recent-history list down to known family
    slugs and preserve order (most-recent first). Defensive: anything
    we don't recognise is dropped silently so a stale stored value
    can't poison the picker.
    """
    if not recent:
        return ()
    return tuple(f for f in recent if f in _CONCEPT_FAMILY_OPTIONS)


def pick_concept_family(
    *,
    brief: dict[str, Any],
    business_kind: str,
    goal: str,
    recent_concept_families: tuple[str, ...] | list[str] | None = None,
) -> str:
    """Pick exactly one concept family for this render.

    Precedence:
      1. `brief["concept_family"]` if it's a known slug AND not in the
         single most-recent slot (we never repeat back-to-back even
         when the brief asks for it — that's the Phase 8.4 contract).
         If the brief asks for it but it IS the most recent, we treat
         it as a soft preference and fall through to the picker.
      2. Walk the goal's preferred list in order, returning the first
         family that's NOT in `recent_concept_families`.
      3. If every preferred family is recent, walk the full 12-family
         pool in declaration order and return the first non-recent.
      4. If every family is recent (caller passed all 12 as history),
         return the LEAST-recent family.
      5. Final fallback: the first preferred family (or
         `customer_transformation` if the goal has no preference list).

    Exported so the caller can pre-resolve the family for logging /
    persistence before the prompt is even built.
    """
    recent = _normalise_recent(recent_concept_families)
    most_recent = recent[0] if recent else None
    recent_set = set(recent)

    # Step 1 — explicit brief field.
    explicit_raw = (brief.get("concept_family") or "").strip().lower().replace(" ", "_")
    if explicit_raw in _CONCEPT_FAMILY_OPTIONS and explicit_raw != most_recent:
        return explicit_raw

    preferred = _GOAL_CONCEPT_PREFERENCE.get(goal, ())

    # Step 2 — walk preferred list.
    for fam in preferred:
        if fam not in recent_set:
            return fam

    # Step 3 — fall through to the full pool.
    for fam in _CONCEPT_FAMILY_OPTIONS:
        if fam not in recent_set:
            return fam

    # Step 4 — every family is recent. Pick the least-recent one.
    # `recent` is most-recent first, so the LAST entry is least recent.
    if recent:
        return recent[-1]

    # Step 5 — total fallback. Goal-preferred head, or default slug.
    if preferred:
        return preferred[0]
    _ = business_kind  # reserved for future business-kind tiebreaks
    return "customer_transformation"


def _concept_family_block(family: str) -> str:
    """Render the CONCEPT FAMILY block — the hook, the scene direction,
    and a stable parseable marker line.

    The marker line (`CONCEPT FAMILY — <slug>`) is what `render.py`
    regex-extracts from prior renders to enforce rotation.
    """
    f = family if family in _CONCEPT_FAMILY_OPTIONS else "customer_transformation"
    label = _CONCEPT_FAMILY_LABELS[f]
    hook = _CONCEPT_FAMILY_HOOKS[f]
    scene = _CONCEPT_FAMILY_SCENE_DIRECTION[f]
    return (
        f"CONCEPT FAMILY — {f}\n"
        f"({label}). HOOK: {hook!s}\n"
        f"Scene direction: {scene}\n"
        "Compose around this concept and this hook. Two consecutive ads "
        "in the same concept family is the single fastest way to fatigue "
        "the audience — this render's concept must be visibly DIFFERENT "
        "from the most recent ones (see rotation context above)."
    )


# Regex used by callers (and tests) to round-trip the chosen family
# back out of a stored prompt. Matches the marker line above.
import re as _re  # noqa: E402 — keep next to the regex it powers

CONCEPT_FAMILY_PROMPT_RE = _re.compile(
    r"^CONCEPT FAMILY — ([a-z_]+)$", _re.MULTILINE
)


def extract_concept_family(prompt: str) -> str | None:
    """Return the concept-family slug embedded in a previously-rendered
    prompt, or `None` if the marker is missing (e.g. a pre-8.4 render).

    Caller — `render.py` uses this to build the `recent_concept_families`
    list for rotation enforcement.
    """
    m = CONCEPT_FAMILY_PROMPT_RE.search(prompt or "")
    if not m:
        return None
    slug = m.group(1)
    return slug if slug in _CONCEPT_FAMILY_OPTIONS else None


def _rotation_context_block(recent_concept_families: tuple[str, ...]) -> str:
    """Tell the model what concepts it just shipped so it can actively
    avoid repeating them. Only renders when we have history.
    """
    recent = _normalise_recent(recent_concept_families)
    if not recent:
        return (
            "ROTATION CONTEXT — this is the first render in this rotation window. "
            "No prior concept families to avoid; pick a concept and ship it boldly."
        )
    chain = " → ".join(_CONCEPT_FAMILY_LABELS[f] for f in recent)
    return (
        f"ROTATION CONTEXT — recent concept families for this business "
        f"(most recent first): {chain}.\n"
        "Do NOT compose another render in any of those families. The viewer "
        "is the same viewer; they've already seen those angles. This render "
        "must come from a visibly DIFFERENT angle so the feed doesn't fatigue."
    )


# Phase 8.2 — performance-first business-context blocks. The DOs are
# the patterns that actually convert for that business kind on paid
# social; the DON'Ts target the high-risk "looks pretty but doesn't
# sell" failure modes the Phase 8.2 brief calls out explicitly.
_BUSINESS_CONTEXT_BLOCKS: dict[str, str] = {
    "restaurant": (
        "BUSINESS CONTEXT — RESTAURANT (performance-first):\n"
        "SHOW: happy customers mid-meal (mid-bite, laughing, raising a glass, leaning in to talk); food being served (the plate landing on the table, the pour, the slice); social atmosphere (occupied tables in the background plane, warm chatter implied through depth-of-field); real tables, real plates, real hands.\n"
        "NEVER: isolated food floating on a plain background; aerial flat-lay-on-marble compositions; luxury fine-dining magazine photography; over-styled plating that looks like a cookbook shoot, not a meal. The Phase 8.2 mandate is explicit on both bans.\n"
        "Conversion rationale: the click comes from 'I want to be at THAT table tonight', not 'I want to study that plate'."
    ),
    "gym": (
        "BUSINESS CONTEXT — GYM / FITNESS (performance-first):\n"
        "SHOW: TRANSFORMATION (before/after visible in the body language, the breath, the focus); EFFORT (sweat sheen, a strained grip, a final rep); PROGRESS (a member at a stage they didn't used to be at); COACHING (a trainer correcting form, a class taking direction).\n"
        "NEVER: bodybuilder photoshoots; fitness-magazine cover poses; airbrushed shredded models flexing at the camera; sterile brand-new showroom shoots with no one in them. The Phase 8.2 mandate is explicit on both bans.\n"
        "Use real members — a range of body types, ages, abilities and ethnicities. The viewer must see THEMSELVES in the frame, not a pro athlete."
    ),
    "real_estate": (
        "BUSINESS CONTEXT — REAL ESTATE (performance-first):\n"
        "SHOW: walkthrough moments (a couple stepping into a room for the first time, an agent guiding a client through the kitchen); client interaction (a consultation at a kitchen island, a handshake in the foyer, keys being handed over); ownership aspiration (a client standing in 'their' future space).\n"
        "NEVER: empty rooms only; sterile magazine-perfect interiors with zero human presence. The Phase 8.2 mandate is explicit on both bans.\n"
        "Architectural integrity still matters: vertical lines stay vertical, perspective lines resolve plausibly — but a HUMAN MOMENT is always in the frame. The click comes from 'I can picture us here', not 'nice cabinetry'."
    ),
    "local_business": (
        "BUSINESS CONTEXT — LOCAL / RETAIL BUSINESS (performance-first):\n"
        "SHOW: owner interacting with a real customer (handing over a product, recommending an item, sharing the story behind it); real products on real shelves or counters; authentic local-shop atmosphere (daylight through the storefront window, plants, signage details out of focus); a secondary customer browsing in the background plane to signal community.\n"
        "NEVER: a sterile catalog product shot disconnected from the venue; staged customer-of-the-month grin-at-camera; empty shop with no one in it.\n"
        "The click comes from 'this feels like a real place run by real people', not 'this looks like an Amazon listing'."
    ),
    "service_business": (
        "BUSINESS CONTEXT — PROFESSIONAL SERVICE (performance-first):\n"
        "Examples in scope: lawyer, accountant, consultant, agency, advisor, coach.\n"
        "SHOW: TRUST (real professional, direct eye contact with the client, calm focused posture); CONSULTATION (laptop or tablet in genuine use mid-conversation, real paper documents, a coffee, mid-discussion gesture); RESULTS (a screen showing a chart that's moving up, a document being signed, a project being handed over).\n"
        "NEVER: overly-corporate stockiness; high-fives over a laptop; call-centre-with-headset framing; suit-and-tie-against-glass-wall hero poses; lone-laptop-on-a-clean-desk product shot. None of those sell a service.\n"
        "The professional looks competent AND warm — dressed for the actual field, never stiff. The click comes from 'I'd trust THEM with my problem'."
    ),
}


# Subject-specific photographic blocks. Each is short and focused on
# the realism levers that matter for THAT subject class.
_SUBJECT_BLOCKS: dict[str, str] = {
    "food": (
        "SUBJECT — FOOD/DRINK:\n"
        "- Render real-food imperfection: uneven crema, slight pour drip down the cup wall, a fingerprint on the rim, crumbs on the saucer, condensation beading on cold glass.\n"
        "- Surface gloss should be specular (sharp highlight from the key light), NOT a uniform sheen.\n"
        "- Visible steam for hot items, visible bubbles in carbonated drinks, visible texture on baked goods (a single broken crust line, an uneven dusting of flour).\n"
        "- Plates / cups: hand-thrown ceramic with slight wall thickness variation. NOT factory-perfect porcelain.\n"
        "- If the subject is mid-action (pour, slice, plating), capture micro-motion — a single drop in flight, knife edge frozen mid-cut."
    ),
    "portrait": (
        "SUBJECT — PEOPLE (in addition to the global HUMAN RULES block):\n"
        "- Eyes: real catchlight from a single direction matching the key light. Slight moisture meniscus on the lower lid. NO glass-eye stare.\n"
        "- Expression: looking off-camera or down at what they're doing — captured between expressions, not at the peak of a posed smile.\n"
        "- Realistic skin tones across diverse ethnicities — no waxy or candy-coloured grading."
    ),
    "product": (
        "SUBJECT — PRODUCT:\n"
        "- Hero angle: three-quarter or slight overhead, subject occupies 40-60% of the frame, with breathing room on at least two sides.\n"
        "- Surface materiality: render the ACTUAL material — brushed aluminium has anisotropic streak highlights, glass has refraction + edge specular, matte plastic has subsurface scatter, leather has grain + slight stretch marks.\n"
        "- Show scale: a subtle scale reference (hand cropped at frame edge, contextual object, surface texture at known size).\n"
        "- Reflections must be physically correct — what's visible in any reflection must match what would actually be there given the camera position. NO impossible mirror-perfect reflections.\n"
        "- Background: a real surface (raw wood, brushed concrete, linen sheet, marble with visible veining), NOT a perfect white cyclorama unless the brief specifically asks for studio."
    ),
    "scene": (
        "SUBJECT — SCENE/ENVIRONMENT:\n"
        "- Architectural integrity: vertical lines stay vertical (correct lens, no tilt-shift distortion unless explicit), perspective lines resolve to plausible vanishing points.\n"
        "- Lived-in details: real wear on floors, scuff marks on walls, plants with imperfect leaves, signage with realistic typography (but NO actual readable text — see CRITICAL block).\n"
        "- Mixed lighting is realistic: practical lamps (warm) + window daylight (cool) create natural temperature contrast across the frame.\n"
        "- Atmosphere: a faint haze, dust in a light beam, slight motion blur on any moving element (a passing figure, a curtain, steam). NEVER perfectly still.\n"
        "- Negative space and depth — let the eye travel into the scene, don't stack everything in the foreground plane."
    ),
    "screen": (
        "SUBJECT — SCREEN/UI (rendered as part of a physical device):\n"
        "- The DEVICE is photographed realistically — show bezel, edge specular, slight screen reflection, ambient room light contributing to glow.\n"
        "- The UI ON the screen: render as abstract geometric shapes and bars only, NO readable text or numbers (the brief will dictate real copy later).\n"
        "- Avoid the standard 'macbook on a desk with coffee and a plant' cliché unless the brief explicitly asks for it.\n"
        "- A real human hand or fingertip on/near the device adds scale + realism — anatomically correct."
    ),
}


# Phase 8.2 — each platform carries an explicit persona alongside the
# aspect / composition note. The persona is what changes the ad's
# CHANCE OF CONVERTING on that platform — not the canvas shape alone.
_SOCIAL_MEDIA_BLOCKS: dict[str, str] = {
    "instagram_feed": (
        "SOCIAL MEDIA OPTIMIZATION — INSTAGRAM FEED (1:1):\n"
        "Persona: SCROLL-STOP / bold visual hook / high-contrast subject / clear hierarchy.\n"
        "- 1:1 square composition. Subject offset by 5-10% from dead-centre so the image reads as composed, not snapshot.\n"
        "- Strong focal point — a single hero element that the eye lands on in under one second.\n"
        "- Bold visual hook — exaggerated colour contrast, a striking gesture, an unexpected angle, or a clear moment frozen in time.\n"
        "- High contrast between subject and background so the ad pops against a feed dominated by faces, food, and screenshots.\n"
        "- Keep the four corners visually quiet (Instagram crops them in some surfaces)."
    ),
    "instagram_reel": (
        "SOCIAL MEDIA OPTIMIZATION — INSTAGRAM REEL / STORY COVER (9:16):\n"
        "Persona: SCROLL-STOP / bold visual hook / high-contrast subject / clear hierarchy — applied to the vertical canvas.\n"
        "- Vertical composition. Hero subject occupies the UPPER TWO-THIRDS so a strong headline overlay can sit in the top band.\n"
        "- Leave the bottom ~15% visually clean for the platform's UI chrome (caption row, swipe affordance).\n"
        "- Composition has obvious vertical hierarchy — eye reads top → middle → bottom in under one second.\n"
        "- Background reads clearly even with side-bezel cropping on tall phone screens."
    ),
    "facebook_ad": (
        "SOCIAL MEDIA OPTIMIZATION — FACEBOOK AD (1.91:1 link card / 1:1 feed):\n"
        "Persona: TRUST-FIRST / RESULT-FIRST.\n"
        "- Lead with what the customer GETS — the result, the moment, the outcome — not the brand or the product packaging.\n"
        "- Trust signals are non-negotiable: real faces, real working environment, real lived-in details. Stock-photo polish kills Facebook conversion.\n"
        "- Single clear subject — no clutter, no competing focal points. The viewer must understand the offer in under one second.\n"
        "- Strong subject-vs-background contrast so the ad doesn't disappear in a busy feed.\n"
        "- Faces and emotional moments outperform static product shots — favour a human subject when the brief allows."
    ),
    "linkedin": (
        "SOCIAL MEDIA OPTIMIZATION — LINKEDIN:\n"
        "Persona: AUTHORITY-FIRST / PROFESSIONAL-FIRST.\n"
        "- The subject reads as a credible expert in their field — posture, attention, environment all signal competence.\n"
        "- Real working environment — a real office, a real workshop, a real meeting room — never a generic stock-photo backdrop.\n"
        "- Restrained colour palette — no neon, no over-saturated grading. Editorial newsroom quality.\n"
        "- Composition reads as a documentary capture, not an obvious ad — LinkedIn audiences distrust salesy visuals."
    ),
}


# Always-on anti-cliché block — targets the most overused stock-photo
# and business-photo poses. Independent of the REJECT block (which
# targets AI render tells specifically).
_ANTI_CLICHE_BLOCK = """\
AVOID THESE CLICHÉS (the visual equivalent of corporate jargon):
- Team members in a meeting room high-fiving over an open laptop.
- Hands typing close-up on a keyboard from above.
- Founder / exec smiling at camera with arms crossed in front of an exposed-brick wall.
- A diverse group of three coworkers looking at a single tablet, all smiling.
- Sticky notes on a glass wall photographed in soft focus.
- "Lightbulb moment" — an actual lightbulb in someone's hand or floating above their head.
- A pristine white desk with a notebook, pen, coffee cup, and plant arranged at 45-degree angles.
- People wearing headsets in a call-centre / customer-service framing.
- Aerial flat-lay of breakfast on a marble counter, perfectly arranged.
- Generic happy customer giving a thumbs-up to the camera.
- "Generic stock-photo feel" — clean, soulless, brand-agnostic, indistinguishable from a thousand other ads.
"""


# REJECT block — AI render tells AND the Phase 8.1 absolute rules.
# Anything listed here also appears in `build_negative_prompt` so the
# image provider gets both a positive suppression directive AND a
# structured negative prompt.
_REJECT_BLOCK = """\
REJECT (Phase 8.1 absolute rules — actively suppress all of these):
- AI art style, cartoon, anime, illustration, painting, watercolour.
- 3D render, CGI, video-game look, plastic / toy aesthetic.
- Over-saturated colour, candy-coloured grading, teal-and-orange grading, neon rim-lights on everything.
- Plastic / airbrushed skin, glass-eye stares, doll-like expressions, symmetrical face geometry, mannequin look.
- Deformed faces, deformed people, unrealistic body proportions, fashion-model poses, fake or frozen smiles, exaggerated expressions.
- Extra fingers, fused fingers, mutated hands, warped hands, broken anatomy.
- Floating objects (every object must have a clear contact shadow / contact point with a surface).
- Random text, readable text, brand logos, made-up brand names, packaging text, signage text, screen text — ANY letters, numbers, or glyphs.
- Watermarks, stock-photo overlays, signature glyphs in a corner, "shutterstock" or "getty"-style branding.
- Generic stock photo feel — soulless, brand-agnostic, smiling-thumbs-up energy.
- "AI sheen": uniformly soft lighting with no shadow direction or fall-off.
- Symmetrical / mirror-perfect reflections where real-world physics wouldn't produce them.
- Impossible geometry — objects clipping through each other, perspectives that don't resolve, multiple contradictory light sources.
- Duplicated subjects when only one was asked for.
- Hexagonal bokeh balls, lens-flare halos, godrays inserted for no reason, floating dust particles as a decoration.
- Default-stylised AI faces (the recognisable "midjourney face" or "stable-diffusion face").
- Fantasy, surrealism, unreal proportions, anything that breaks the "this could have been a real photograph" rule.
"""


# Structured negative prompt fed separately to the image provider via
# `ImageRenderRequest.negative_prompt`. Kept comma-separated and tight
# so providers that have a literal negative-prompt field get the
# strongest signal. Exported for tests.
NEGATIVE_PROMPT = (
    "cartoon, anime, illustration, painting, watercolor, "
    "3d render, cgi, video game, toy, plastic aesthetic, "
    "unrealistic, plastic skin, airbrushed skin, doll-like, mannequin, "
    "symmetrical face, glass-eye stare, "
    "deformed face, deformed person, fashion-model pose, influencer pose, "
    "fake smile, frozen smile, exaggerated expression, "
    "extra fingers, fused fingers, mutated hands, warped hands, broken anatomy, "
    "floating objects, "
    "text, letters, numbers, glyphs, watermark, logo artifacts, signature, "
    "oversaturated, candy color, teal-orange grading, neon rim light, "
    "fantasy, surreal, unreal proportions, "
    "stock photo look, generic ad, soulless, "
    "blurry, low quality, low resolution, jpeg artifacts, "
    "ai art, midjourney face, stable-diffusion face"
)


# ---------------------------------------------------------------------
#  Aspect-aware composition guidance. Just stating the aspect isn't
#  enough — the model needs to know what to DO with the canvas shape.
# ---------------------------------------------------------------------


def _aspect_composition_note(aspect: str) -> str:
    a = _normalize_aspect(aspect)
    if a == "1:1":
        return (
            "Square canvas: balanced central composition is OK, but still offset the subject "
            "by ~5-10% from dead-centre. Keep distractions out of the four corners."
        )
    if a == "4:5":
        return (
            "Tall canvas (4:5): place the subject's primary mass in the middle-third vertically. "
            "Leave breathing room at top (atmosphere / context) and bottom (CTA / overlay zone)."
        )
    if a == "9:16":
        return (
            "Phone-vertical (9:16): strong vertical hierarchy. Hero subject occupies the upper "
            "two-thirds; bottom third stays visually clean for swipe-up / overlay copy. "
            "Background must read clearly even with phone-side-bezel cropping."
        )
    if a == "16:9":
        return (
            "Wide canvas (16:9): horizontal storytelling. Place the subject off the central axis "
            "(left- or right-third) and let the remaining horizontal space carry environmental "
            "context. Avoid stacking elements vertically."
        )
    if a == "3:2":
        return (
            "Classic 35mm landscape (3:2): rule-of-thirds intersections. Treat foreground / "
            "midground / background as three distinct depth layers."
        )
    if a == "1.91:1":
        return (
            "Facebook / link-card (1.91:1): single dominant subject in the left- or right-third. "
            "Centre band carries the emotional moment; the opposite third stays clean for "
            "CTA / overlay copy."
        )
    return f"Aspect ratio: {aspect}. Compose for that canvas shape, not a square crop."


# ---------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------


def build_image_prompt(
    *,
    brief: dict[str, Any],
    profile: BusinessProfileResponse,
    platform: str | None = None,
    visual_type: str | None = None,
    recent_concept_families: tuple[str, ...] | list[str] | None = None,
) -> str:
    """Compose the rendered-image prompt from an AdCreativeBrief dict.

    Accepts a raw dict (the visual's `output` JSONB) rather than a
    Pydantic model so this works against legacy briefs too. Missing
    fields gracefully fall back to sensible defaults.

    Phase 8.1: photographic agency-quality realism is the absolute
    default. There is no longer a permissive illustrative branch.
    The `platform` and `visual_type` kwargs are optional context the
    caller (the render endpoint) plumbs through from `GeneratedVisual`
    so we can add a platform-specific social-media-optimisation block.

    Phase 8.4: the optional `recent_concept_families` kwarg is the
    list of concept-family slugs the caller has shipped for this
    business in recent renders (most-recent first). The picker uses
    it to enforce ad-fatigue rotation. Default `None` = no rotation
    pressure (back-compat for callers that haven't been wired yet).
    """
    # `visual_type` is accepted for forwards-compatibility (e.g. when
    # we eventually want reel-cover vs ad-creative-specific tweaks).
    # Reserved + name-mangled so static-analysis doesn't flag it.
    _ = visual_type

    ai_prompt = (brief.get("ai_image_prompt") or "").strip()
    aspect = brief.get("aspect_ratio") or "1:1"
    aspect_note = _aspect_composition_note(aspect)

    palette_lines: list[str] = []
    for swatch in brief.get("color_palette") or []:
        if isinstance(swatch, dict):
            name = swatch.get("name", "")
            hex_code = swatch.get("hex", "")
            role = swatch.get("role", "")
            if hex_code:
                palette_lines.append(
                    f"{name or 'colour'} {hex_code} ({role or 'accent'})"
                )
    palette = "; ".join(palette_lines) or "warm neutrals with one accent pop"

    audience_snippet = profile.target_audience[:160] + (
        "..." if len(profile.target_audience) > 160 else ""
    )

    # When the visual generator produced an agency-grade prompt, use it as
    # the primary scene direction and only append render-pipeline constraints.
    if len(ai_prompt) >= 40:
        return f"""\
{_PERFORMANCE_HEADER}

Agency art direction — follow this scene composition closely:
{ai_prompt}

Business: {profile.business_name}, a {profile.industry} business.
Audience: {audience_snippet}
Aspect ratio: {aspect}. {aspect_note}
Colour palette (use these hex codes — do not invent new colours): {palette}.

CRITICAL — FINAL OUTPUT STANDARD:
- DO NOT render any text, letters, numbers, or glyphs in the image. Text overlays will be added in post-production.
- Mobile-first composition — the hero must read clearly at 360x450 px.
- Output a single coherent image, not a grid or contact sheet.
- This is NOT AI art. NOT stock photography. NOT a design showcase.
""".strip()

    focal = brief.get("focal_subject") or "a product hero shot"
    layout = brief.get("composition_layout") or "centered composition"
    hierarchy = (
        " → ".join(brief.get("visual_hierarchy") or [])
        or "(no hierarchy specified)"
    )
    mood = ", ".join(brief.get("mood_keywords") or []) or "calm, premium, honest"
    aesthetic = (
        brief.get("reference_aesthetic")
        or "modern editorial brand photography"
    )

    # Trust upgrade T2 — strip any embedded "Text: 'X'" / "with the
    # label 'Y'" instructions before forwarding to the image renderer.
    # The brief may mention overlay text, but the renderer is
    # explicitly told to draw zero text — those two directives must
    # not contradict.
    raw_cta_placement = (
        brief.get("cta_placement") or "lower third with high contrast"
    )
    cta_placement = strip_overlay_text_instructions(raw_cta_placement)

    typography = brief.get("typography") or {}
    typo_style = (
        typography.get("style", "") if isinstance(typography, dict) else ""
    )
    typo_brief = typo_style or "modern editorial sans-serif"

    # Phase 4-A optional fields — only mention them in the prompt when
    # present so legacy briefs stay clean.
    mobile_note = brief.get("mobile_readability_note")
    safe_margin = brief.get("safe_text_margin")
    overlay_cap = brief.get("overlay_text_max_words")

    extras: list[str] = []
    if mobile_note:
        extras.append(f"Mobile legibility: {mobile_note}")
    if safe_margin:
        extras.append(f"Keep text-safe margin clear: {safe_margin}")
    if overlay_cap:
        extras.append(
            "Leave breathing room for a future text overlay of "
            f"at most {overlay_cap} words."
        )
    extras_block = ("\n".join(extras) + "\n") if extras else ""

    # Subject-specific block — only injected when the focal subject
    # matches a known class.
    subject_class = _subject_class(focal)
    subject_block = ""
    if subject_class:
        subject_block = "\n" + _SUBJECT_BLOCKS[subject_class] + "\n"

    # Business-context block — keyed on the founder's industry.
    business_kind = _business_kind(profile.industry)
    business_context_block = ""
    if business_kind:
        business_context_block = (
            "\n" + _BUSINESS_CONTEXT_BLOCKS[business_kind] + "\n"
        )

    # Human-rules block — fires for portrait subjects, scene subjects
    # that imply people, or industries (gym, restaurant, real-estate,
    # service) where humans are part of the brand promise.
    human_block = ""
    if _people_in_frame(focal, business_kind):
        human_block = "\n" + _HUMAN_RULES_BLOCK + "\n"

    # Social-media-optimisation block — keyed on platform + aspect.
    platform_kind = _platform_kind(platform, aspect)
    social_block = ""
    if platform_kind:
        social_block = "\n" + _SOCIAL_MEDIA_BLOCKS[platform_kind] + "\n"

    # Phase 8.3 — outcome-driven layer. Pick the goal, derive the
    # funnel stage from it (or from explicit brief input), and bucket
    # the audience. These three classifiers together feed the
    # outcome-shaping blocks AND bias the emotion picker downstream.
    goal = _pick_goal(brief=brief, business_kind=business_kind)
    funnel_stage = _pick_funnel_stage(brief=brief, goal=goal)
    audience = _pick_audience(profile)

    # Phase 8.4 — creative-diversity layer. Pick the concept family
    # for this render. The picker is rotation-aware: if the caller
    # plumbed `recent_concept_families` from prior renders, the same
    # family won't be picked back-to-back.
    concept_family = pick_concept_family(
        brief=brief,
        business_kind=business_kind,
        goal=goal,
        recent_concept_families=recent_concept_families,
    )
    rotation_block = _rotation_context_block(
        _normalise_recent(recent_concept_families)
    )

    # Phase 8.2 + 8.3 — pick the single primary emotion this ad must
    # trigger. The funnel stage now feeds the bias when the brief is
    # silent on emotion. See `_pick_emotion` for the precedence policy.
    emotion = _pick_emotion(
        brief=brief, business_kind=business_kind, funnel_stage=funnel_stage
    )

    return f"""\
{_PERFORMANCE_HEADER}

A high-performing paid-social ad creative for {profile.business_name}, a {profile.industry} business.
Audience: {audience_snippet}

{_goal_block(goal)}

{rotation_block}

{_concept_family_block(concept_family)}

{_funnel_block(funnel_stage)}

{_audience_block(business_kind=business_kind, audience=audience)}

Focal subject: {focal}.
Composition: {layout}.
Aspect ratio: {aspect}. {aspect_note}
Visual hierarchy (in order): {hierarchy}.
CTA placement zone: {cta_placement}. Leave that zone visually clean so a CTA button can be overlaid in post-production.

Colour palette (use these hex codes — do not invent new colours): {palette}.
Typography reference: {typo_brief}.
Mood: {mood}. Reference aesthetic: {aesthetic}.

{_emotion_block(emotion)}

{extras_block}{_PHOTOGRAPHIC_REALISM_BLOCK}{subject_block}{business_context_block}{human_block}
{_MARKETING_RULES_BLOCK}{social_block}
{_COMPOSITION_RULE_BLOCK}
{_META_ADS_LIBRARY_BLOCK}
{_ANTI_CLICHE_BLOCK}
{_REJECT_BLOCK}
{_CONVERSION_GATE_BLOCK}
CRITICAL — FINAL OUTPUT STANDARD:
- DO NOT render any text, letters, numbers, or glyphs in the image. Text overlays will be added in post-production from the brief's recommended copy.
- Mobile-first composition — the hero must read clearly at 360x450 px.
- Output a single coherent image, not a grid or contact sheet.
- This is NOT AI art. NOT stock photography. NOT a design showcase. The output is a high-performing paid-ad creative that a small-business owner would confidently publish and spend ad budget on TODAY.
- Pass ALL SIX Conversion Gate tests before finalising — scroll-stop, conversion, $5k-agency, OUTCOME, FOUNDER, CREATIVE UNIQUENESS. If any one fails, re-plan the composition.
- THE IMAGE IS NOT THE PRODUCT. THE BUSINESS OUTCOME IS THE PRODUCT. Every compositional choice must serve the desired business outcome ({_GOAL_LABELS[goal]}). If you cannot answer "what action will the customer take after seeing this — call / book / buy / visit / message?" in a single word, re-plan the composition.
- CONCEPT FAMILY this render must deliver: {_CONCEPT_FAMILY_LABELS[concept_family]} (slug: {concept_family}). The viewer has already seen the most-recent families listed in ROTATION CONTEXT — this render must come from a visibly DIFFERENT angle so a founder can ship 20 ads in a row without feed-fatigue.
""".strip()


def build_negative_prompt(*, brief: dict[str, Any]) -> str:
    """Return the structured negative prompt fed separately to the
    image provider.

    The positive prompt also names everything in the REJECT block, but
    a separate negative-prompt field gives providers (Stable Diffusion,
    Imagen, some OpenAI surfaces) a stronger suppression signal — they
    weight negative-prompt tokens differently from in-line "avoid X"
    instructions.

    Currently `brief` is unused — the negative list is universal under
    Phase 8.1. Kept as a kwarg so future iterations (per-subject-class
    negatives, e.g. extra food-specific rejections) can attach without
    a signature change.
    """
    _ = brief
    return NEGATIVE_PROMPT


def brief_dict_for_render(
    *,
    visual_type: str,
    output: dict[str, Any],
    slide_index: int | None = None,
) -> dict[str, Any]:
    """Map a stored visual brief into the ad-creative-shaped dict
    `build_image_prompt` expects. Keeps render.py free of per-type
    branching beyond dispatch."""
    if visual_type == "carousel":
        slides = output.get("slide_designs") or []
        if slide_index is None:
            slide_index = 0
        if not slides or slide_index >= len(slides):
            return {**output, "focal_subject": output.get("cover_concept") or "carousel cover"}
        slide = slides[slide_index]
        total = len(slides)
        focal = slide.get("visual") or output.get("cover_concept") or "carousel slide"
        if slide_index == total - 1 and output.get("cta_slide_concept"):
            focal = f"{focal}. CTA slide: {output['cta_slide_concept']}"
        palette = output.get("design_system_palette") or output.get("color_palette") or []
        typography = output.get("design_system_typography") or output.get("typography") or {}
        return {
            "aspect_ratio": output.get("aspect_ratio") or "1:1",
            "focal_subject": focal,
            "composition_layout": (
                f"Carousel slide {slide_index + 1} of {total} — "
                f"{slide.get('text_treatment') or 'editorial layout'}"
            ),
            "color_palette": palette,
            "typography": typography,
            "visual_hierarchy": [
                f"Slide {slide_index + 1} hero",
                slide.get("text_treatment") or "supporting detail",
                "swipe cue to next" if slide_index < total - 1 else "final CTA moment",
            ],
            "cta_placement": "lower third with contrast" if slide_index == total - 1 else "clear overlay zone",
            "mood_keywords": output.get("mood_keywords")
            or ["premium", "scroll-stopping", "cohesive"],
            "reference_aesthetic": output.get("reference_aesthetic")
            or "paid social carousel, editorial commercial photography",
            "mobile_readability_note": (
                f"Slide {slide_index + 1} must read instantly in a 6-inch feed."
            ),
        }

    if visual_type == "thumbnail":
        typography = output.get("typography") or {}
        return {
            "aspect_ratio": output.get("aspect_ratio") or "16:9",
            "focal_subject": output.get("focal_subject") or "bold thumbnail subject",
            "composition_layout": output.get("contrast_strategy")
            or "high-contrast thumbnail composition",
            "color_palette": output.get("color_palette") or [],
            "typography": typography,
            "visual_hierarchy": [
                output.get("focal_subject") or "hero subject",
                output.get("background_treatment") or "background",
                "click magnet",
            ],
            "cta_placement": "none — thumbnail frame only",
            "mood_keywords": ["bold", "high contrast", "feed-stopping"],
            "reference_aesthetic": output.get("background_treatment")
            or "YouTube thumbnail, punchy commercial",
            "mobile_readability_note": output.get("mobile_legibility_note"),
            "overlay_text_max_words": 5,
        }

    # ad_creative — output already matches AdCreativeBriefFull shape.
    return output


def ad_output_to_brief(*, ad_type: str, output: dict[str, Any]) -> dict[str, Any]:
    """Synthesize an ad-creative brief dict from a generated ad payload."""
    creative = (
        output.get("creative_direction")
        or output.get("hook")
        or output.get("primary_text")
        or output.get("caption")
        or output.get("intro_text")
        or ""
    )
    headline = (
        output.get("headline")
        or (output.get("headlines") or [""])[0]
        or output.get("description")
        or ""
    )
    focal = creative or headline or "commercial product hero shot"
    aspect = "9:16" if ad_type == "instagram_promo" else "4:5" if ad_type in ("meta", "linkedin") else "1:1"
    return {
        "aspect_ratio": aspect,
        "focal_subject": focal,
        "composition_layout": "centered paid-social ad composition with clear hero",
        "color_palette": [
            {"name": "Primary", "hex": "#1a1a2e", "role": "background"},
            {"name": "Accent", "hex": "#e94560", "role": "CTA pop"},
            {"name": "Neutral", "hex": "#f5f5f5", "role": "breathing room"},
        ],
        "typography": {
            "style": "modern bold sans-serif",
            "headline_treatment": "bold uppercase",
            "body_treatment": "clean readable",
            "suggested_fonts": ["Inter", "Helvetica Neue"],
        },
        "visual_hierarchy": [
            focal[:80] if focal else "hero product",
            headline[:60] if headline else "headline zone",
            output.get("cta_button") or output.get("cta_sticker_text") or "CTA",
        ],
        "cta_placement": "lower third, high contrast button zone",
        "mood_keywords": ["premium", "conversion-focused", "scroll-stopping"],
        "reference_aesthetic": "high-performing paid social ad, editorial commercial photography",
        "mobile_readability_note": "Hero readable at phone scale in Meta/IG feed.",
        "overlay_text_max_words": 6,
        "safe_text_margin": "bottom 20% reserved for CTA overlay",
    }
