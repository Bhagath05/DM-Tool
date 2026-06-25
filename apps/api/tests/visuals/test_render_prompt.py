"""Phase 8.1 + 8.2 + 8.3 — render-prompt builder tests.

Phase 8.1 locked in REALISM (no AI / cartoon / CGI; Sony A7R V vocab;
anatomically correct hands; structured negative prompt).

Phase 8.2 layered PERFORMANCE on top:
  - Optimisation target shifts from "looks real" to "outperforms
    typical small-business ads on Instagram and Facebook."
  - Every image carries exactly ONE primary emotion (curiosity /
    urgency / desire / trust / aspiration / FOMO), picked
    deterministically from the brief.
  - The 1-second test replaces the 3-second test for WHAT / WHO / WHY.
  - Industry blocks ship sharper DOs/DON'Ts (no floating food, no
    bodybuilder photoshoots, no empty rooms, no call-centre framing).
  - Social-media blocks carry a platform PERSONA (IG = scroll-stop,
    FB = trust + result, LinkedIn = authority).
  - A 70/20/10 composition rule and a three-test CONVERSION GATE
    (scroll-stop / conversion / $5k-agency) close out every prompt.

Phase 8.3 layers OUTCOME on top of that:
  - New hierarchy: business → BUSINESS GOAL → AUDIENCE → FUNNEL STAGE
    → platform → image.
  - Nine canonical goals (Lead Gen, Phone Calls, WhatsApp, Bookings,
    Store Visits, Sales, Brand Awareness, Retargeting, Upselling),
    each with its own visual strategy (problem+solution / experience /
    product outcome / identity / proof / premium outcome / etc.).
  - Three funnel stages (TOF = attention / curiosity / aspiration;
    MOF = trust / before-after / authority; BOF = conversion /
    urgency / clear offer). The emotion picker is now biased by stage.
  - Audience buckets (families / young adults / professionals /
    couples / seniors / students / general) crossed with business
    kind to surface a SPECIFIC scene per audience.
  - Meta Ads Library mode: social proof / clear offer / customer
    outcome / emotional hook required; generic-stock and generic-
    smiling-people patterns explicitly banned.
  - Conversion gate extended to FIVE tests — adds OUTCOME ("what
    business result is this image trying to create?") and FOUNDER
    ("if this succeeds, what action will the customer take?").
  - Final rule: the image is NOT the product, the business outcome
    is the product.

These tests pin all three layers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.visuals.render_prompt import (
    _AUDIENCE_OPTIONS,
    _CONCEPT_FAMILY_HOOKS,
    _CONCEPT_FAMILY_LABELS,
    _CONCEPT_FAMILY_OPTIONS,
    _EMOTION_OPTIONS,
    _GOAL_LABELS,
    _GOAL_OPTIONS,
    NEGATIVE_PROMPT,
    _business_kind,
    _people_in_frame,
    _pick_audience,
    _pick_emotion,
    _pick_funnel_stage,
    _pick_goal,
    _platform_kind,
    _subject_class,
    build_image_prompt,
    build_negative_prompt,
    extract_concept_family,
    pick_concept_family,
)

# ----------------------------------------------------------------------
#  Fixtures
# ----------------------------------------------------------------------


def _profile(
    *,
    business_name: str = "Acme Roasters",
    industry: str = "Specialty coffee shop",
    target_audience: str = (
        "Coffee enthusiasts and remote workers aged 25-40 who care about "
        "single-origin beans and a warm neighbourhood third place."
    ),
) -> BusinessProfileResponse:
    """Build a BusinessProfileResponse without touching the DB.

    Pure dict-validate path — keeps the test runnable in a unit
    environment with no Postgres / no Clerk / no auth context.
    """
    return BusinessProfileResponse.model_validate(
        {
            "id": uuid.uuid4(),
            "user_id": "user_test",
            "organization_id": uuid.uuid4(),
            "brand_id": uuid.uuid4(),
            "business_name": business_name,
            "industry": industry,
            "target_audience": target_audience,
            "brand_tone": "warm",
            "competitors": [],
            "goals": ["build awareness"],
            "preferred_platforms": ["Instagram"],
            "analysis_status": "completed",
            "analysis": None,
            "analysis_error": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )


def _brief(**overrides) -> dict:
    """A minimal valid brief dict — overrides win."""
    base = {
        "focal_subject": "a latte being poured by a barista",
        "composition_layout": "rule of thirds, subject in left third",
        "visual_hierarchy": ["the latte", "barista's hands", "warm cafe interior"],
        "aspect_ratio": "1:1",
        "mood_keywords": ["warm", "authentic", "morning ritual"],
        "reference_aesthetic": "documentary lifestyle photography",
        "color_palette": [
            {"name": "warm cream", "hex": "#F4E8D8", "role": "background"},
            {"name": "espresso brown", "hex": "#3B2415", "role": "subject"},
        ],
        "typography": {"style": "modern editorial sans-serif"},
        "cta_placement": "lower-right with high contrast",
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
#  Agency ai_image_prompt — preferred when present
# ----------------------------------------------------------------------


class TestAgencyImagePrompt:
    def test_ai_image_prompt_becomes_primary_scene_direction(self):
        agency = (
            "Editorial photograph of a Hyderabad student holding a UK university "
            "offer letter, warm golden-hour window light, shallow depth of field, "
            "trustworthy study-abroad consultancy aesthetic, 4:5 Instagram feed."
        )
        prompt = build_image_prompt(
            brief=_brief(ai_image_prompt=agency),
            profile=_profile(),
        )
        assert "Agency art direction" in prompt
        assert agency in prompt
        assert "DO NOT render any text" in prompt

    def test_short_ai_image_prompt_falls_back_to_full_pipeline(self):
        prompt = build_image_prompt(
            brief=_brief(ai_image_prompt="coffee shop"),
            profile=_profile(),
        )
        assert "Focal subject:" in prompt
        assert "Agency art direction" not in prompt


# ----------------------------------------------------------------------
#  Performance / realism header — Phase 8.2 reframes the prologue
# ----------------------------------------------------------------------


class TestPerformanceHeader:
    def test_performance_framing_leads_the_prompt(self):
        # Phase 8.2 — performance comes BEFORE realism. The first
        # ~200 chars must establish that this is a paid-ad creative
        # engineered to outperform typical small-business ads, not
        # a generic "make it look real" instruction.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        head = prompt[:300]
        assert "PERFORMANCE-FIRST PAID-AD CREATIVE" in head
        assert "OUTPERFORM" in head
        assert "Instagram" in head and "Facebook" in head
        assert "CLICKS" in head or "LEADS" in head

    def test_realism_execution_standard_still_in_the_prologue(self):
        # Phase 8.1 carry-forward — Sony A7R V / Canon EOS R5 +
        # "no AI render / cartoon / 3D / CGI" stay in the opening
        # paragraph so the diffusion model gets the realism signal
        # alongside the performance framing.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        head = prompt[:1000]
        assert "ULTRA-REALISTIC COMMERCIAL PHOTOGRAPHY" in head
        assert "Sony A7R V" in head
        assert "Canon EOS R5" in head
        # Lowercase the head before matching so the assertion is robust
        # to small wording tweaks ("never an AI render" vs "no AI render").
        head_lc = head.lower()
        assert "never an ai render" in head_lc
        assert "cartoon" in head_lc
        assert "3d render" in head_lc

    def test_references_meta_ads_library_and_dtc_brands(self):
        # The Phase 8.2 brief explicitly tells us to study patterns
        # from Meta Ads Library, top-performing Facebook ads, direct-
        # response advertising, and modern DTC brands. Surface those
        # references so the model anchors on the right population of
        # winners instead of generic "ad photography."
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        head = prompt[:1000]
        assert "Meta Ads Library" in head
        assert "DTC" in head or "direct-response" in head

    def test_names_the_realism_boosters_verbatim(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        # Phase 8.1 carry-forward — the realism boosters live in the
        # photographic-realism block and must still appear verbatim.
        for booster in (
            "professional commercial photography",
            "captured on Sony A7R V",
            "ultra realistic",
            "agency quality",
            "real-world lighting",
            "natural skin texture",
            "authentic environment",
            "photorealistic",
        ):
            assert booster in prompt, f"Missing booster: {booster!r}"


# ----------------------------------------------------------------------
#  REJECT block — Phase 8.1 absolute rules
# ----------------------------------------------------------------------


class TestRejectBlock:
    @pytest.fixture
    def prompt(self) -> str:
        return build_image_prompt(brief=_brief(), profile=_profile())

    @pytest.mark.parametrize(
        "term",
        [
            "ai art",
            "cartoon",
            "anime",
            "illustration",
            "painting",
            "watercolour",  # British spelling used in the block
            "3d render",
            "cgi",
            "plastic",
            "airbrushed",
            "deformed",
            "fashion-model pose",
            "fake or frozen smiles",
            "extra fingers",
            "fused fingers",
            "mutated hands",
            "floating objects",
            "watermark",  # appears as "Watermarks"
            "stock-photo",
            "over-saturated",
            "fantasy",  # appears as "Fantasy"
            "unreal proportions",
            "doll-like",
        ],
    )
    def test_reject_block_names_phase_81_banned_terms(self, prompt: str, term: str):
        # Case-insensitive — many bans appear at sentence-start with
        # capitalised first letter (e.g. "Watermarks", "Fantasy"). The
        # SUPPRESSION signal is the same either way, and the structured
        # `NEGATIVE_PROMPT` already enforces the lowercase canonical
        # form on the provider side.
        assert term in prompt.lower(), f"REJECT block missing banned term: {term!r}"

    def test_critical_block_still_forbids_in_image_text(self, prompt: str):
        assert "DO NOT render any text" in prompt
        assert "letters" in prompt


# ----------------------------------------------------------------------
#  Marketing rules — "3-second test"
# ----------------------------------------------------------------------


class TestMarketingRules:
    def test_marketing_contract_block_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "MARKETING CONTRACT" in prompt
        assert "WHAT" in prompt
        assert "WHO" in prompt
        assert "WHY" in prompt
        # Phase 8.2 — tightened from 3 seconds to ONE second.
        assert "ONE SECOND" in prompt or "1-second" in prompt
        # And the old 3-second wording must NOT regress.
        assert "3 seconds" not in prompt
        assert "three seconds" not in prompt.lower()


# ----------------------------------------------------------------------
#  Industry / business-context branching
# ----------------------------------------------------------------------


class TestBusinessContext:
    @pytest.mark.parametrize(
        "industry,expected_kind",
        [
            ("Restaurant", "restaurant"),
            ("Local cafe", "restaurant"),
            ("Specialty coffee shop", "restaurant"),
            ("Bakery", "restaurant"),
            ("Gym", "gym"),
            ("Fitness studio", "gym"),
            ("CrossFit box", "gym"),
            ("Yoga studio", "gym"),
            ("Real estate brokerage", "real_estate"),
            ("Realtor", "real_estate"),
            ("Property management", "real_estate"),
            ("B2B SaaS", "service_business"),
            ("Marketing consulting", "service_business"),
            ("Law firm", "service_business"),
            ("Boutique", "local_business"),
            ("Local barber", "local_business"),
            ("Florist", "local_business"),
        ],
    )
    def test_business_kind_classifier(self, industry: str, expected_kind: str):
        assert _business_kind(industry) == expected_kind

    def test_unknown_industry_returns_empty_string(self):
        # Anything we don't have a rule for falls back to no block —
        # the rest of the prompt still works.
        assert _business_kind("Aerospace propulsion R&D") == ""

    def test_restaurant_prompt_injects_restaurant_block(self):
        # Phase 8.2 — restaurant block must SHOW customers + service +
        # social atmosphere AND must explicitly ban the floating-food
        # cliche and the luxury-fine-dining cliche.
        prompt = build_image_prompt(
            brief=_brief(), profile=_profile(industry="Restaurant")
        )
        assert "BUSINESS CONTEXT — RESTAURANT" in prompt
        assert "happy customers" in prompt
        assert "food being served" in prompt
        assert "social atmosphere" in prompt
        # Phase 8.2 DON'Ts — both banned visual patterns must be named.
        assert "isolated food floating" in prompt
        assert "fine-dining" in prompt.lower()
        # Cross-industry leakage must not happen.
        assert "BUSINESS CONTEXT — GYM" not in prompt
        assert "BUSINESS CONTEXT — REAL ESTATE" not in prompt

    def test_gym_prompt_injects_gym_block(self):
        # Phase 8.2 — gym block must lead with TRANSFORMATION / EFFORT /
        # PROGRESS / COACHING and explicitly ban the bodybuilder shoot.
        prompt = build_image_prompt(
            brief=_brief(focal_subject="kettlebell mid-swing"),
            profile=_profile(industry="CrossFit gym"),
        )
        assert "BUSINESS CONTEXT — GYM" in prompt
        for must_have in ("TRANSFORMATION", "EFFORT", "PROGRESS", "COACHING"):
            assert must_have in prompt
        # Phase 8.2 DON'Ts — both banned patterns must be named.
        assert "bodybuilder photoshoots" in prompt
        assert "fitness-magazine" in prompt or "fitness magazine" in prompt

    def test_real_estate_prompt_injects_real_estate_block(self):
        # Phase 8.2 — real-estate block must lead with walkthrough /
        # client interaction / ownership aspiration and explicitly ban
        # the empty-rooms-only shoot.
        prompt = build_image_prompt(
            brief=_brief(focal_subject="modern kitchen interior"),
            profile=_profile(industry="Real Estate brokerage"),
        )
        assert "BUSINESS CONTEXT — REAL ESTATE" in prompt
        assert "walkthrough moments" in prompt
        assert "client interaction" in prompt
        assert "ownership aspiration" in prompt
        # Phase 8.2 DON'T — empty-rooms-only is explicitly banned.
        assert "empty rooms only" in prompt

    def test_service_business_prompt_injects_service_block(self):
        # Phase 8.2 — service block must lead with TRUST / CONSULTATION
        # / RESULTS and name the four canonical examples.
        prompt = build_image_prompt(
            brief=_brief(focal_subject="consultant and client at a table"),
            profile=_profile(industry="Marketing consultancy"),
        )
        assert "BUSINESS CONTEXT — PROFESSIONAL SERVICE" in prompt
        for must_have in ("TRUST", "CONSULTATION", "RESULTS"):
            assert must_have in prompt
        for example in ("lawyer", "accountant", "consultant", "agency"):
            assert example in prompt
        # Phase 8.2 DON'Ts.
        assert "high-fives" in prompt
        assert "call-centre" in prompt or "call centre" in prompt

    def test_local_business_prompt_injects_local_block(self):
        prompt = build_image_prompt(
            brief=_brief(focal_subject="owner handing customer a product"),
            profile=_profile(industry="Local boutique"),
        )
        assert "BUSINESS CONTEXT — LOCAL" in prompt


# ----------------------------------------------------------------------
#  Human rules
# ----------------------------------------------------------------------


class TestHumanRules:
    def test_human_rules_fire_for_explicit_portrait_subjects(self):
        prompt = build_image_prompt(
            brief=_brief(focal_subject="founder portrait"),
            profile=_profile(industry="Aerospace"),
        )
        assert "PEOPLE — must look real" in prompt
        assert "anatomically correct" in prompt
        assert "fashion-model" in prompt or "fashion-model pose" in prompt
        assert "fake or frozen smiles" in prompt

    def test_human_rules_fire_for_implicit_people_scenes(self):
        # "workout session" implies a person even though the focal
        # subject string doesn't carry the word "person".
        prompt = build_image_prompt(
            brief=_brief(focal_subject="morning workout session"),
            profile=_profile(industry="Aerospace"),
        )
        assert "PEOPLE — must look real" in prompt

    def test_human_rules_fire_for_human_industries(self):
        # Restaurants get human rules even when the focal subject is a
        # plate of food — there are still people in the dining room.
        prompt = build_image_prompt(
            brief=_brief(focal_subject="pizza on a wooden board"),
            profile=_profile(industry="Restaurant"),
        )
        assert "PEOPLE — must look real" in prompt

    def test_human_rules_skip_when_no_people_implied(self):
        # A pure product shot in an aerospace business shouldn't drag
        # in the human rules block — it'd waste tokens.
        prompt = build_image_prompt(
            brief=_brief(focal_subject="a stainless steel bottle on a wood surface"),
            profile=_profile(industry="Aerospace"),
        )
        assert "PEOPLE — must look real" not in prompt


# ----------------------------------------------------------------------
#  Subject + platform classification
# ----------------------------------------------------------------------


class TestSubjectAndPlatform:
    @pytest.mark.parametrize(
        "focal,expected",
        [
            ("laptop dashboard interface", "screen"),
            ("brushed aluminium bottle", "product"),
            ("a latte being poured", "food"),
            ("founder portrait", "portrait"),
            ("modern kitchen interior", "scene"),
        ],
    )
    def test_subject_classifier(self, focal: str, expected: str):
        assert _subject_class(focal) == expected

    def test_subject_classifier_returns_empty_when_no_match(self):
        assert _subject_class("abstract conceptual idea") == ""

    @pytest.mark.parametrize(
        "platform,aspect,expected",
        [
            ("Instagram", "1:1", "instagram_feed"),
            ("Instagram", "9:16", "instagram_reel"),
            ("Instagram", "4:5", "instagram_reel"),  # tall IG content
            ("Facebook", "1.91:1", "facebook_ad"),
            ("LinkedIn", "1:1", "linkedin"),
            ("TikTok", "9:16", "instagram_reel"),
            (None, "1:1", "instagram_feed"),  # aspect-only inference
            (None, "9:16", "instagram_reel"),
            (None, "1.91:1", "facebook_ad"),
            (None, "16:9", ""),  # no rule
        ],
    )
    def test_platform_classifier(
        self, platform: str | None, aspect: str, expected: str
    ):
        assert _platform_kind(platform, aspect) == expected

    def test_social_media_block_for_instagram_feed(self):
        prompt = build_image_prompt(
            brief=_brief(aspect_ratio="1:1"),
            profile=_profile(),
            platform="Instagram",
        )
        assert "SOCIAL MEDIA OPTIMIZATION — INSTAGRAM FEED" in prompt

    def test_social_media_block_for_reel(self):
        prompt = build_image_prompt(
            brief=_brief(aspect_ratio="9:16"),
            profile=_profile(),
            platform="Instagram",
        )
        assert "SOCIAL MEDIA OPTIMIZATION — INSTAGRAM REEL" in prompt
        assert "headline overlay" in prompt or "headline" in prompt

    def test_social_media_block_for_linkedin(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(),
            platform="LinkedIn",
        )
        assert "SOCIAL MEDIA OPTIMIZATION — LINKEDIN" in prompt
        assert "professional" in prompt.lower()


# ----------------------------------------------------------------------
#  People-implied helper — small unit test for the truth table
# ----------------------------------------------------------------------


class TestPeopleInFrame:
    @pytest.mark.parametrize(
        "focal,industry,expected",
        [
            ("founder portrait", "", True),  # explicit person
            ("morning workout session", "", True),  # implicit
            ("pizza on a wooden board", "restaurant", True),  # industry
            ("modern kitchen interior", "real_estate", True),
            ("a stainless bottle", "aerospace", False),  # no signal
            ("abstract pattern", "", False),
        ],
    )
    def test_truth_table(self, focal: str, industry: str, expected: bool):
        # `industry` argument here is already the canonical business
        # kind (the function consumes the output of `_business_kind`).
        assert _people_in_frame(focal, industry) is expected


# ----------------------------------------------------------------------
#  Defaults + graceful degradation
# ----------------------------------------------------------------------


class TestDefaults:
    def test_minimal_brief_still_renders_a_safe_prompt(self):
        """An almost-empty brief shouldn't break the builder — Phase 4
        legacy briefs sometimes lack the optional fields.

        Phase 8.2 — the safety blocks (performance framing, realism
        manifesto, REJECT block, emotion block, composition rule,
        conversion gate) must all still appear so an old brief still
        produces a conversion-grade prompt.
        """
        prompt = build_image_prompt(brief={}, profile=_profile())
        assert "PERFORMANCE-FIRST PAID-AD CREATIVE" in prompt
        assert "ULTRA-REALISTIC" in prompt
        assert "REJECT" in prompt
        assert "EMOTIONAL INTENT" in prompt
        assert "COMPOSITION RULE — 70 / 20 / 10" in prompt
        assert "CONVERSION GATE" in prompt
        assert "warm neutrals" in prompt  # default palette fallback
        assert "1:1" in prompt  # default aspect

    def test_palette_with_missing_hex_is_filtered(self):
        """If a swatch arrives without a hex it shouldn't pollute the
        palette line — that's how earlier versions produced 'colour
        (accent); colour (accent); ...' garbage."""
        prompt = build_image_prompt(
            brief=_brief(
                color_palette=[
                    {"name": "no hex", "role": "background"},
                    {"name": "real", "hex": "#abcdef", "role": "accent"},
                ]
            ),
            profile=_profile(),
        )
        assert "#abcdef" in prompt
        # The no-hex swatch shouldn't surface as a dangling entry.
        assert "no hex" not in prompt

    def test_long_target_audience_is_truncated(self):
        long_audience = "Coffee enthusiasts " * 50  # ~950 chars
        prompt = build_image_prompt(
            brief=_brief(), profile=_profile(target_audience=long_audience)
        )
        # We cap at 160 chars + "..." — full string shouldn't appear.
        assert long_audience.strip() not in prompt
        assert "..." in prompt


# ----------------------------------------------------------------------
#  Negative prompt — structured suppression list
# ----------------------------------------------------------------------


class TestNegativePrompt:
    def test_constant_covers_all_phase_81_bans(self):
        wanted = [
            "cartoon",
            "anime",
            "illustration",
            "painting",
            "watercolor",
            "3d render",
            "cgi",
            "plastic skin",
            "deformed face",
            "extra fingers",
            "mutated hands",
            "blurry",
            "low quality",
            "watermark",
            "oversaturated",
            "fantasy",
            "fake smile",
            "stock photo look",
            "floating objects",
        ]
        lowered = NEGATIVE_PROMPT.lower()
        for term in wanted:
            assert term in lowered, f"Negative prompt missing: {term!r}"

    def test_build_negative_prompt_returns_the_constant(self):
        assert build_negative_prompt(brief={}) == NEGATIVE_PROMPT
        # Brief is unused today but the kwarg shape stays stable.
        assert build_negative_prompt(brief=_brief()) == NEGATIVE_PROMPT


# ----------------------------------------------------------------------
#  Phase 8.2 — EMOTIONAL INTENT block + deterministic picker
# ----------------------------------------------------------------------


class TestEmotionalIntent:
    def test_six_allowed_emotions_are_canonical_set(self):
        # The Phase 8.2 brief names exactly these six emotions.
        assert set(_EMOTION_OPTIONS) == {
            "curiosity",
            "urgency",
            "desire",
            "trust",
            "aspiration",
            "fomo",
        }

    def test_explicit_brief_emotion_wins(self):
        # An upstream brief LLM may set `emotional_intent` directly —
        # that always overrides our inference rules.
        for e in _EMOTION_OPTIONS:
            assert _pick_emotion(brief={"emotional_intent": e}, business_kind="") == e

    def test_invalid_explicit_emotion_falls_back_to_inference(self):
        # An unrecognised emotion must not corrupt the pipeline; we
        # silently drop it and fall through to the inference rules.
        picked = _pick_emotion(
            brief={"emotional_intent": "anger", "goal": "Generate leads now"},
            business_kind="",
        )
        assert picked in _EMOTION_OPTIONS

    @pytest.mark.parametrize(
        "goal,expected",
        [
            ("Limited-time launch this weekend only", "urgency"),
            ("Everyone in town has joined — don't miss out", "fomo"),
            ("Build trust with first-time customers via testimonials", "trust"),
            ("Show the transformation our coaching delivers", "aspiration"),
            ("Tease the secret behind our best dish", "curiosity"),
            ("Make our new pastry look irresistible and delicious", "desire"),
        ],
    )
    def test_goal_keywords_drive_emotion_inference(self, goal: str, expected: str):
        assert _pick_emotion(brief={"goal": goal}, business_kind="") == expected

    @pytest.mark.parametrize(
        "business_kind,expected",
        [
            ("restaurant", "desire"),
            ("gym", "aspiration"),
            ("real_estate", "aspiration"),
            ("service_business", "trust"),
            ("local_business", "trust"),
        ],
    )
    def test_industry_default_emotion(self, business_kind: str, expected: str):
        # With no brief signal at all, the industry default kicks in.
        assert _pick_emotion(brief={}, business_kind=business_kind) == expected

    def test_final_fallback_is_curiosity(self):
        # Empty brief + unknown industry — the safest scroll-stop default.
        assert _pick_emotion(brief={}, business_kind="") == "curiosity"

    def test_emotion_block_appears_in_prompt(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "EMOTIONAL INTENT" in prompt
        # The chosen emotion must be named in uppercase as the single
        # primary intent.
        assert any(e.upper() in prompt for e in _EMOTION_OPTIONS)

    def test_restaurant_brief_picks_desire_by_default(self):
        # End-to-end: a restaurant brief with no emotion hints should
        # surface DESIRE as the named intent.
        prompt = build_image_prompt(
            brief=_brief(), profile=_profile(industry="Restaurant")
        )
        assert "DESIRE" in prompt

    def test_urgency_keyword_in_goal_overrides_industry_default(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Limited-time weekend brunch — ends Sunday"),
            profile=_profile(industry="Restaurant"),
        )
        assert "URGENCY" in prompt
        assert "DESIRE" not in prompt  # industry default is overridden


# ----------------------------------------------------------------------
#  Phase 8.2 — 70/20/10 composition rule
# ----------------------------------------------------------------------


class TestCompositionRule:
    def test_composition_block_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "COMPOSITION RULE — 70 / 20 / 10" in prompt
        assert "70%" in prompt
        assert "20%" in prompt
        assert "10%" in prompt
        # Explicit anti-clutter rule.
        assert "Avoid clutter" in prompt
        assert "Avoid multiple focal points" in prompt


# ----------------------------------------------------------------------
#  Phase 8.2 — Conversion gate (scroll-stop, conversion, $5k-agency)
# ----------------------------------------------------------------------


class TestConversionGate:
    def test_gate_block_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "CONVERSION GATE" in prompt

    def test_gate_names_all_three_tests(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        # The Phase 8.2 brief enumerates the exact three questions —
        # they must all surface verbatim so the model can self-check.
        assert "SCROLL-STOP TEST" in prompt
        assert "CONVERSION TEST" in prompt
        assert "AGENCY-QUALITY TEST" in prompt
        # And the agency price tag is the explicit benchmark.
        assert "$5,000" in prompt


# ----------------------------------------------------------------------
#  Phase 8.2 — Final output standard (not AI / not stock / not showcase)
# ----------------------------------------------------------------------


class TestFinalOutputStandard:
    def test_critical_block_names_what_the_output_is_not(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        # Phase 8.2 explicitly demands the prompt close by stating what
        # the output is NOT.
        tail = prompt[-1500:]
        assert "NOT AI art" in tail
        assert "NOT stock photography" in tail
        assert "NOT a design showcase" in tail

    def test_critical_block_names_what_the_output_is(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        tail = prompt[-1500:]
        # A high-performing paid-ad creative — verbatim from the brief.
        assert "high-performing paid-ad creative" in tail.lower()
        # And spending ad budget is the conversion-readiness benchmark.
        assert "ad budget" in tail.lower()

    def test_critical_block_references_conversion_gate(self):
        # The final block tells the model to actually apply the three
        # tests — without that, the conversion gate is decorative.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        tail = prompt[-1500:]
        assert "Conversion Gate" in tail
        assert "re-plan" in tail.lower()


# ----------------------------------------------------------------------
#  Phase 8.2 — Social-media personas
# ----------------------------------------------------------------------


class TestSocialMediaPersona:
    def test_instagram_feed_carries_scroll_stop_persona(self):
        prompt = build_image_prompt(
            brief=_brief(aspect_ratio="1:1"),
            profile=_profile(),
            platform="Instagram",
        )
        assert "INSTAGRAM FEED" in prompt
        # The persona keywords from the Phase 8.2 brief.
        assert "SCROLL-STOP" in prompt
        assert "bold visual hook" in prompt
        assert "High contrast" in prompt or "high-contrast" in prompt.lower()

    def test_facebook_ad_carries_trust_first_persona(self):
        prompt = build_image_prompt(
            brief=_brief(aspect_ratio="1.91:1"),
            profile=_profile(),
            platform="Facebook",
        )
        assert "FACEBOOK AD" in prompt
        # The persona keywords — both trust and result-first.
        assert "TRUST-FIRST" in prompt
        assert "RESULT-FIRST" in prompt

    def test_linkedin_carries_authority_first_persona(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(),
            platform="LinkedIn",
        )
        assert "LINKEDIN" in prompt
        assert "AUTHORITY-FIRST" in prompt
        assert "PROFESSIONAL-FIRST" in prompt


# ======================================================================
#                       PHASE 8.3 — Outcome-driven
# ======================================================================
#
# Hierarchy: business → BUSINESS GOAL → AUDIENCE → FUNNEL STAGE
#            → platform → image.
# ======================================================================


# ----------------------------------------------------------------------
#  Phase 8.3 — Business goal classifier (9 canonical goals)
# ----------------------------------------------------------------------


class TestBusinessGoalClassifier:
    def test_nine_canonical_goals_are_the_brief_set(self):
        # The Phase 8.3 brief names exactly nine goals — pin the set
        # so a refactor can't silently drop one.
        assert set(_GOAL_OPTIONS) == {
            "lead_generation",
            "phone_calls",
            "whatsapp_messages",
            "bookings",
            "store_visits",
            "product_sales",
            "brand_awareness",
            "retargeting",
            "upselling",
        }

    def test_every_goal_has_a_human_label(self):
        # The labels are what we surface to the diffusion model — every
        # canonical slug must have a non-empty label.
        for slug in _GOAL_OPTIONS:
            assert _GOAL_LABELS[slug]
            assert len(_GOAL_LABELS[slug]) >= 4

    def test_explicit_business_goal_wins(self):
        for g in _GOAL_OPTIONS:
            assert (
                _pick_goal(brief={"business_goal": g}, business_kind="")
                == g
            )

    def test_explicit_goal_accepts_human_label_with_spaces(self):
        # "Phone Calls" → "phone_calls" — the slug-by-replacing-spaces
        # path must work because human dropdowns send the label.
        assert (
            _pick_goal(
                brief={"business_goal": "Phone Calls"}, business_kind=""
            )
            == "phone_calls"
        )

    @pytest.mark.parametrize(
        "goal_text,expected",
        [
            ("Get more bookings this weekend", "bookings"),
            ("Drive WhatsApp enquiries", "whatsapp_messages"),
            ("Get more phone calls this week", "phone_calls"),
            ("Increase walk-in traffic to the store", "store_visits"),
            ("Generate qualified leads via free consult", "lead_generation"),
            ("Brand awareness for our new launch", "brand_awareness"),
            ("Retarget warm audience that bounced", "retargeting"),
            ("Upsell existing members to the premium tier", "upselling"),
            ("Drive product sales this week", "product_sales"),
            ("Get more reservations on Friday", "bookings"),
        ],
    )
    def test_goal_text_drives_classification(
        self, goal_text: str, expected: str
    ):
        assert _pick_goal(brief={"goal": goal_text}, business_kind="") == expected

    @pytest.mark.parametrize(
        "business_kind,expected",
        [
            ("restaurant", "bookings"),
            ("gym", "lead_generation"),
            ("real_estate", "lead_generation"),
            ("service_business", "lead_generation"),
            ("local_business", "store_visits"),
        ],
    )
    def test_industry_default_goal(self, business_kind: str, expected: str):
        # With no brief signal, the industry default fires.
        assert _pick_goal(brief={}, business_kind=business_kind) == expected

    def test_final_fallback_is_lead_generation(self):
        # Empty brief + unknown industry — safest small-business default.
        assert _pick_goal(brief={}, business_kind="") == "lead_generation"


# ----------------------------------------------------------------------
#  Phase 8.3 — BUSINESS GOAL + VISUAL STRATEGY block in the prompt
# ----------------------------------------------------------------------


class TestGoalBlock:
    def test_goal_block_appears_with_visual_strategy(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "BUSINESS GOAL" in prompt
        assert "VISUAL STRATEGY" in prompt
        # The named goal must surface verbatim.
        assert any(label in prompt for label in _GOAL_LABELS.values())

    def test_lead_generation_strategy_is_problem_plus_solution(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Get more leads via free consult"),
            profile=_profile(),
        )
        assert "Lead Generation" in prompt
        assert "PROBLEM + SOLUTION" in prompt

    def test_bookings_strategy_is_experience(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
        )
        assert "Bookings" in prompt
        assert "EXPERIENCE" in prompt

    def test_sales_strategy_is_product_outcome(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Drive product sales this week"),
            profile=_profile(),
        )
        assert "Product Sales" in prompt
        assert "PRODUCT OUTCOME" in prompt

    def test_brand_awareness_strategy_is_identity(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Brand awareness for our launch"),
            profile=_profile(),
        )
        assert "Brand Awareness" in prompt
        assert "IDENTITY" in prompt

    def test_retargeting_strategy_is_proof(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Retarget warm audience"),
            profile=_profile(),
        )
        assert "Retargeting" in prompt
        assert "PROOF" in prompt

    def test_upselling_strategy_is_premium_outcome(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Upsell existing customers to premium tier"),
            profile=_profile(),
        )
        assert "Upselling Existing Customers" in prompt
        assert "PREMIUM OUTCOME" in prompt

    def test_phone_calls_strategy_is_direct_contact(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Get more phone calls"),
            profile=_profile(),
        )
        assert "Phone Calls" in prompt
        assert "DIRECT CONTACT" in prompt

    def test_whatsapp_strategy_is_fast_response(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Drive WhatsApp messages"),
            profile=_profile(),
        )
        assert "WhatsApp Messages" in prompt
        assert "FAST RESPONSE" in prompt

    def test_store_visits_strategy_is_in_store_moment(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Drive more walk-in foot traffic"),
            profile=_profile(),
        )
        assert "Store Visits" in prompt
        assert "IN-STORE MOMENT" in prompt


# ----------------------------------------------------------------------
#  Phase 8.3 — Funnel-stage classifier + block
# ----------------------------------------------------------------------


class TestFunnelStage:
    @pytest.mark.parametrize(
        "explicit,expected",
        [
            ("top", "top"),
            ("TOF", "top"),
            ("awareness", "top"),
            ("middle", "middle"),
            ("MOF", "middle"),
            ("consideration", "middle"),
            ("bottom", "bottom"),
            ("BOF", "bottom"),
            ("conversion", "bottom"),
            ("purchase", "bottom"),
        ],
    )
    def test_explicit_brief_stage_wins(self, explicit: str, expected: str):
        assert (
            _pick_funnel_stage(
                brief={"funnel_stage": explicit}, goal="lead_generation"
            )
            == expected
        )

    @pytest.mark.parametrize(
        "goal,expected",
        [
            ("brand_awareness", "top"),
            ("lead_generation", "middle"),
            ("retargeting", "middle"),
            ("bookings", "bottom"),
            ("phone_calls", "bottom"),
            ("whatsapp_messages", "bottom"),
            ("store_visits", "bottom"),
            ("product_sales", "bottom"),
            ("upselling", "bottom"),
        ],
    )
    def test_goal_drives_funnel_stage(self, goal: str, expected: str):
        assert _pick_funnel_stage(brief={}, goal=goal) == expected

    def test_unknown_goal_falls_back_to_middle(self):
        assert _pick_funnel_stage(brief={}, goal="unknown_goal_slug") == "middle"

    def test_top_of_funnel_block_in_prompt(self):
        # Brand awareness → TOF → "ATTENTION" + curiosity/aspiration cues.
        prompt = build_image_prompt(
            brief=_brief(goal="Brand awareness for our launch"),
            profile=_profile(),
        )
        assert "FUNNEL STAGE — TOP OF FUNNEL" in prompt
        assert "ATTENTION" in prompt
        assert "CURIOSITY" in prompt or "ASPIRATION" in prompt
        assert "SOCIAL PROOF" in prompt

    def test_middle_of_funnel_block_in_prompt(self):
        # Lead generation → MOF → "TRUST" + before/after / authority cues.
        prompt = build_image_prompt(
            brief=_brief(goal="Generate leads via free consult"),
            profile=_profile(),
        )
        assert "FUNNEL STAGE — MIDDLE OF FUNNEL" in prompt
        assert "TRUST" in prompt
        assert "BEFORE/AFTER" in prompt or "AUTHORITY" in prompt

    def test_bottom_of_funnel_block_in_prompt(self):
        # Bookings → BOF → "CONVERSION" + clear offer / next action cues.
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
        )
        assert "FUNNEL STAGE — BOTTOM OF FUNNEL" in prompt
        assert "CONVERSION" in prompt
        assert "BOOKING" in prompt or "PURCHASE" in prompt or "INQUIRY" in prompt


# ----------------------------------------------------------------------
#  Phase 8.3 — Audience classifier + audience-shaped scene block
# ----------------------------------------------------------------------


class TestAudienceClassifier:
    def test_seven_canonical_audience_buckets(self):
        assert set(_AUDIENCE_OPTIONS) == {
            "families",
            "young_adults",
            "professionals",
            "couples",
            "seniors",
            "students",
            "general",
        }

    @pytest.mark.parametrize(
        "audience_text,expected",
        [
            ("Families with young children", "families"),
            ("Parents and their kids", "families"),
            ("Young couples on date night", "couples"),
            ("Retirees and seniors aged 65+", "seniors"),
            ("College students on a budget", "students"),
            ("Corporate professionals and remote workers", "professionals"),
            ("Millennials aged 25-34 who love coffee", "young_adults"),
        ],
    )
    def test_audience_text_drives_bucket(
        self, audience_text: str, expected: str
    ):
        assert (
            _pick_audience(_profile(target_audience=audience_text))
            == expected
        )

    def test_unknown_audience_falls_back_to_general(self):
        assert (
            _pick_audience(_profile(target_audience="Aerospace propulsion engineers"))
            == "general"
        )

    def test_restaurant_families_audience_renders_family_scene(self):
        # The exact Phase 8.3 example: restaurant + families →
        # parents + children enjoying a meal.
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(
                industry="Restaurant",
                target_audience="Families with young children",
            ),
        )
        assert "AUDIENCE — this ad is for: families" in prompt
        # The scene direction must explicitly name parents + children.
        assert "Parents and children" in prompt

    def test_restaurant_young_adults_audience_renders_social_scene(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(
                industry="Restaurant",
                target_audience="Young adults aged 25-34 looking for nightlife",
            ),
        )
        assert "AUDIENCE — this ad is for: young adults" in prompt
        # The scene direction must lean social.
        assert "friends" in prompt and "social" in prompt.lower()

    def test_restaurant_professionals_audience_renders_lunch_meeting(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(
                industry="Restaurant",
                target_audience="Corporate professionals and executives",
            ),
        )
        assert "AUDIENCE — this ad is for: professionals" in prompt
        # The scene direction must reference the working-lunch frame.
        assert "working lunch" in prompt.lower() or "lunch meeting" in prompt.lower()

    def test_general_audience_falls_back_to_broad_block(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(
                industry="Restaurant",
                target_audience="Aerospace propulsion engineers",
            ),
        )
        assert "AUDIENCE — broad / general consumer" in prompt


# ----------------------------------------------------------------------
#  Phase 8.3 — Funnel-stage bias on the emotion picker
# ----------------------------------------------------------------------


class TestFunnelStageEmotionBias:
    def test_top_of_funnel_biases_towards_curiosity_or_aspiration(self):
        # With a silent brief and no industry default, a TOF stage
        # should pull the emotion into the TOF preferred set.
        e = _pick_emotion(
            brief={}, business_kind="", funnel_stage="top"
        )
        assert e in {"curiosity", "aspiration"}

    def test_middle_of_funnel_biases_towards_trust_or_aspiration(self):
        e = _pick_emotion(
            brief={}, business_kind="", funnel_stage="middle"
        )
        assert e in {"trust", "aspiration"}

    def test_bottom_of_funnel_biases_towards_urgency_desire_fomo(self):
        e = _pick_emotion(
            brief={}, business_kind="", funnel_stage="bottom"
        )
        assert e in {"urgency", "desire", "fomo"}

    def test_funnel_bias_respects_industry_default_when_compatible(self):
        # Restaurant's industry-default emotion is "desire". For a BOF
        # campaign (which prefers urgency/desire/FOMO), the picker
        # should keep the industry default — it's already in the
        # preferred family.
        e = _pick_emotion(
            brief={}, business_kind="restaurant", funnel_stage="bottom"
        )
        assert e == "desire"

    def test_funnel_bias_overrides_industry_when_incompatible(self):
        # Restaurant's industry-default is "desire" (BOF-shaped). For
        # a TOF campaign (which prefers curiosity/aspiration), "desire"
        # is NOT in the preferred set — the funnel bias should win and
        # pick the first TOF-preferred emotion.
        e = _pick_emotion(
            brief={}, business_kind="restaurant", funnel_stage="top"
        )
        assert e in {"curiosity", "aspiration"}
        assert e != "desire"

    def test_explicit_brief_emotion_beats_funnel_bias(self):
        # The brief is sacred — explicit emotion wins over every
        # downstream signal including the funnel stage.
        e = _pick_emotion(
            brief={"emotional_intent": "fomo"},
            business_kind="restaurant",
            funnel_stage="top",
        )
        assert e == "fomo"

    def test_brand_awareness_campaign_picks_tof_emotion_end_to_end(self):
        # End-to-end: a brand-awareness brief should land a TOF-family
        # emotion in the rendered prompt.
        prompt = build_image_prompt(
            brief=_brief(goal="Brand awareness for our launch"),
            profile=_profile(),
        )
        # Either CURIOSITY or ASPIRATION must be the named intent.
        assert ("CURIOSITY" in prompt) or ("ASPIRATION" in prompt)


# ----------------------------------------------------------------------
#  Phase 8.3 — Meta Ads Library mode
# ----------------------------------------------------------------------


class TestMetaAdsLibraryMode:
    def test_meta_ads_block_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "META ADS LIBRARY MODE" in prompt

    def test_meta_ads_block_names_the_four_winning_patterns(self):
        # The Phase 8.3 brief names these four explicitly.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        for pattern in (
            "SOCIAL PROOF",
            "CLEAR OFFER",
            "CUSTOMER OUTCOME",
            "EMOTIONAL HOOK",
        ):
            assert pattern in prompt

    def test_meta_ads_block_bans_generic_stock_and_smiling_people(self):
        # The Phase 8.3 brief explicitly bans these two losing patterns.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        # Lowercased match for robustness against minor wording shifts.
        lc = prompt.lower()
        assert "generic stock photography" in lc
        assert "generic smiling people" in lc


# ----------------------------------------------------------------------
#  Phase 8.3 — Five-test conversion gate (adds OUTCOME + FOUNDER)
# ----------------------------------------------------------------------


class TestFiveTestConversionGate:
    """The original Phase 8.3 five-test gate — pinned here even though
    Phase 8.4 extends it to six (see `TestSixTestConversionGate`
    below). The 8.3 trio of new tests (outcome / founder / phase-8.2
    trio survival) must still hold.
    """

    def test_outcome_test_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "OUTCOME TEST" in prompt
        # The exact question from the Phase 8.3 brief.
        assert "What business result is this image trying to create" in prompt

    def test_founder_test_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "FOUNDER TEST" in prompt
        # The exact question.
        assert "what action will the customer take" in prompt
        # The five expected one-word answers.
        for action in ("CALL", "BOOK", "BUY", "VISIT", "MESSAGE"):
            assert action in prompt

    def test_phase_82_trio_survives(self):
        # Phase 8.4 swaps "ALL FIVE" → "ALL SIX" in the gate text but
        # the three Phase 8.2 tests themselves must still be named.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "SCROLL-STOP TEST" in prompt
        assert "CONVERSION TEST" in prompt
        assert "AGENCY-QUALITY TEST" in prompt


# ----------------------------------------------------------------------
#  Phase 8.3 — Final rule: the image is not the product
# ----------------------------------------------------------------------


class TestPhase83FinalRule:
    def test_image_is_not_the_product_rule_in_critical_block(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
        )
        tail = prompt[-2000:]
        # The Phase 8.3 final rule must appear verbatim (caps for
        # weight) in the CRITICAL block.
        assert "THE IMAGE IS NOT THE PRODUCT" in tail
        assert "THE BUSINESS OUTCOME IS THE PRODUCT" in tail

    def test_critical_block_names_the_specific_goal(self):
        # The CRITICAL block reminds the model which goal it's serving.
        prompt = build_image_prompt(
            brief=_brief(goal="Get more phone calls today"),
            profile=_profile(),
        )
        tail = prompt[-2000:]
        assert "Phone Calls" in tail

    def test_critical_block_lists_the_five_one_word_actions(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        tail = prompt[-2000:]
        # The "call / book / buy / visit / message" reminder in the
        # final rule.
        for action in ("call", "book", "buy", "visit", "message"):
            assert action in tail.lower()


# ----------------------------------------------------------------------
#  Phase 8.3 — Outcome-driven end-to-end smoke test
# ----------------------------------------------------------------------


class TestOutcomeDrivenEndToEnd:
    def test_restaurant_families_bookings_renders_coherent_outcome_chain(self):
        # The full Phase 8.3 hierarchy stacked end-to-end:
        # business=restaurant, goal=bookings, audience=families,
        # funnel=bottom (bookings → BOF), emotion biased by BOF.
        prompt = build_image_prompt(
            brief=_brief(goal="Book a family table this weekend"),
            profile=_profile(
                industry="Restaurant",
                target_audience="Families with young children",
            ),
        )
        # Goal layer.
        assert "Bookings" in prompt
        assert "EXPERIENCE" in prompt
        # Funnel layer (bottom).
        assert "BOTTOM OF FUNNEL" in prompt
        # Audience layer (families → parents + children scene).
        assert "Parents and children" in prompt
        # Emotion layer — BOF + restaurant industry-default → DESIRE.
        assert "DESIRE" in prompt
        # Meta Ads + five-test gate close.
        assert "META ADS LIBRARY MODE" in prompt
        assert "OUTCOME TEST" in prompt
        assert "FOUNDER TEST" in prompt
        # Phase 8.3 final rule.
        assert "THE IMAGE IS NOT THE PRODUCT" in prompt

    def test_gym_professionals_leadgen_renders_a_different_outcome_chain(self):
        # Same renderer, completely different outcome chain.
        prompt = build_image_prompt(
            brief=_brief(goal="Generate leads via free trial"),
            profile=_profile(
                industry="CrossFit gym",
                target_audience="Corporate professionals who want to train before work",
            ),
        )
        assert "Lead Generation" in prompt
        assert "PROBLEM + SOLUTION" in prompt
        assert "MIDDLE OF FUNNEL" in prompt
        assert "AUDIENCE — this ad is for: professionals" in prompt
        # Professional gym scene hint includes "before-work session".
        assert "before-work session" in prompt.lower()


# ======================================================================
#                      PHASE 8.4 — Creative Diversity
# ======================================================================
#
# A founder must be able to ship 20 ads in a row without the feed
# feeling repetitive. The Concept Engine picks ONE of twelve concept
# families per render, and the picker is rotation-aware (the caller
# plumbs the most recent N families and the picker excludes them).
# ======================================================================


# ----------------------------------------------------------------------
#  Phase 8.4 — Twelve canonical concept families
# ----------------------------------------------------------------------


class TestConceptFamilyCatalog:
    def test_twelve_canonical_families_are_the_brief_set(self):
        # The Phase 8.4 brief names exactly these twelve families. Pin
        # the set so a refactor can't silently drop one.
        assert set(_CONCEPT_FAMILY_OPTIONS) == {
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
        }

    def test_every_family_has_a_human_label(self):
        for slug in _CONCEPT_FAMILY_OPTIONS:
            assert _CONCEPT_FAMILY_LABELS[slug]
            assert len(_CONCEPT_FAMILY_LABELS[slug]) >= 4

    def test_every_family_has_a_hook_line(self):
        # The Hook Engine — one short scroll-stop line per family.
        for slug in _CONCEPT_FAMILY_OPTIONS:
            hook = _CONCEPT_FAMILY_HOOKS[slug]
            assert hook and hook.endswith((".", "?"))

    def test_phase_84_canonical_hook_lines_present(self):
        # The Phase 8.4 brief calls these out verbatim (slight word
        # variants are fine, but the SPIRIT must be there).
        assert "changed" in _CONCEPT_FAMILY_HOOKS["before_after"].lower()
        assert "everyone" in _CONCEPT_FAMILY_HOOKS["social_proof"].lower()
        assert "experts" in _CONCEPT_FAMILY_HOOKS["authority_positioning"].lower()
        assert "imagine" in _CONCEPT_FAMILY_HOOKS["lifestyle_aspiration"].lower()
        assert "struggling" in _CONCEPT_FAMILY_HOOKS["problem_awareness"].lower()


# ----------------------------------------------------------------------
#  Phase 8.4 — Picker: rotation, precedence, fallbacks
# ----------------------------------------------------------------------


class TestPickConceptFamily:
    def test_explicit_brief_family_wins_when_not_most_recent(self):
        # Brief asks for a specific family AND it's not the most-recent
        # one → use it.
        for f in _CONCEPT_FAMILY_OPTIONS:
            picked = pick_concept_family(
                brief={"concept_family": f},
                business_kind="",
                goal="lead_generation",
                recent_concept_families=("offer_driven",) if f != "offer_driven" else ("authority_positioning",),
            )
            assert picked == f

    def test_explicit_brief_family_with_spaces_is_normalised(self):
        # "Customer Transformation" → "customer_transformation".
        picked = pick_concept_family(
            brief={"concept_family": "Customer Transformation"},
            business_kind="",
            goal="lead_generation",
        )
        assert picked == "customer_transformation"

    def test_explicit_brief_family_dropped_when_it_is_most_recent(self):
        # Phase 8.4 contract — never repeat back-to-back, even if the
        # brief explicitly asks for it. Fall through to the picker.
        picked = pick_concept_family(
            brief={"concept_family": "social_proof"},
            business_kind="",
            goal="bookings",
            recent_concept_families=("social_proof",),
        )
        assert picked != "social_proof"

    def test_goal_preference_drives_pick_with_no_history(self):
        # No recent history, no explicit brief — first preferred family
        # for the goal must win.
        # Lead Gen's first preferred family is `problem_awareness`.
        picked = pick_concept_family(
            brief={}, business_kind="", goal="lead_generation"
        )
        assert picked == "problem_awareness"

    def test_picker_skips_recently_used_families_in_preferred_list(self):
        # Bookings prefers lifestyle_aspiration first; if that's recent
        # the picker must walk to the next preferred family.
        picked = pick_concept_family(
            brief={},
            business_kind="restaurant",
            goal="bookings",
            recent_concept_families=("lifestyle_aspiration",),
        )
        # Next in bookings' preferred list is `social_proof`.
        assert picked == "social_proof"

    def test_picker_walks_full_preferred_list_then_falls_back(self):
        # Exhaust all bookings-preferred families in recent history;
        # picker should fall through to the wider 12-family pool.
        bookings_preferred = (
            "lifestyle_aspiration",
            "social_proof",
            "customer_transformation",
            "authority_positioning",
            "offer_driven",
            "community",
        )
        picked = pick_concept_family(
            brief={},
            business_kind="restaurant",
            goal="bookings",
            recent_concept_families=bookings_preferred,
        )
        # Must NOT be any of the preferred set.
        assert picked not in bookings_preferred
        # Must be a valid family.
        assert picked in _CONCEPT_FAMILY_OPTIONS

    def test_picker_least_recent_when_all_twelve_are_recent(self):
        # Pathological case — caller passes every family as recent.
        # Picker must return the LEAST-recent (last item in the list).
        all_twelve = _CONCEPT_FAMILY_OPTIONS  # arbitrary order
        picked = pick_concept_family(
            brief={},
            business_kind="",
            goal="lead_generation",
            recent_concept_families=all_twelve,
        )
        # The least-recent slot is the last element of `recent`.
        assert picked == all_twelve[-1]

    def test_invalid_explicit_family_falls_back_to_inference(self):
        # An unknown slug from the brief must NOT poison the pipeline.
        picked = pick_concept_family(
            brief={"concept_family": "nonsense_family"},
            business_kind="",
            goal="bookings",
        )
        # Should be the goal default (bookings → lifestyle_aspiration).
        assert picked == "lifestyle_aspiration"

    def test_stale_recent_history_with_unknown_slug_is_dropped(self):
        # If a stored prompt has a typo'd family in the marker, the
        # normaliser must drop it so it can't lock out a legitimate
        # pick.
        picked = pick_concept_family(
            brief={},
            business_kind="",
            goal="bookings",
            recent_concept_families=("not_a_real_family",),
        )
        # The normaliser drops the unknown slug, so bookings'
        # first-preferred lifestyle_aspiration must still win.
        assert picked == "lifestyle_aspiration"

    def test_unknown_goal_falls_back_to_first_family(self):
        picked = pick_concept_family(
            brief={}, business_kind="", goal="not_a_real_goal"
        )
        # No goal-preference list → fall through to the wider pool's
        # first slug in declaration order (customer_transformation).
        assert picked == "customer_transformation"


# ----------------------------------------------------------------------
#  Phase 8.4 — Goal-shaped concept preferences (the brief's examples)
# ----------------------------------------------------------------------


class TestGoalConceptAlignment:
    @pytest.mark.parametrize(
        "goal,expected_first",
        [
            # Phase 8.4 brief's example: gym + leads → Transformation
            # is one of the headline angles; we map lead_generation's
            # FIRST preferred family to problem_awareness (problem-
            # aware framing is the highest-leverage lead-gen angle).
            ("lead_generation", "problem_awareness"),
            # Phase 8.4: restaurant + bookings → lifestyle leads.
            ("bookings", "lifestyle_aspiration"),
            # Phase 8.4: real-estate + phone calls → authority leads.
            ("phone_calls", "authority_positioning"),
            # Brand awareness → founder story leads (the Phase 8.3
            # outcome-chain hand-off).
            ("brand_awareness", "founder_story"),
            # Retargeting → testimonial leads (warm audience).
            ("retargeting", "customer_testimonial"),
            # Upselling → transformation leads (existing customers
            # want the next tier).
            ("upselling", "customer_transformation"),
            # Product sales → product demo leads.
            ("product_sales", "product_demonstration"),
            # Store visits → community leads (local-shop energy).
            ("store_visits", "community"),
            # WhatsApp → behind-the-scenes leads (intimate channel).
            ("whatsapp_messages", "behind_the_scenes"),
        ],
    )
    def test_goal_first_preference(self, goal: str, expected_first: str):
        picked = pick_concept_family(
            brief={}, business_kind="", goal=goal
        )
        assert picked == expected_first


# ----------------------------------------------------------------------
#  Phase 8.4 — CONCEPT FAMILY block in the prompt
# ----------------------------------------------------------------------


class TestConceptFamilyBlock:
    def test_concept_family_block_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "CONCEPT FAMILY" in prompt

    def test_concept_block_carries_a_hook(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "HOOK:" in prompt

    def test_concept_block_carries_scene_direction(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "Scene direction:" in prompt

    def test_concept_block_names_the_picked_family_in_human_label(self):
        # Bookings → lifestyle_aspiration → "Lifestyle Aspiration"
        # human label must surface verbatim.
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
        )
        assert "Lifestyle Aspiration" in prompt

    def test_concept_block_is_marked_with_parseable_slug(self):
        # The render.py rotation query relies on this stable token.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        slug = extract_concept_family(prompt)
        assert slug is not None
        assert slug in _CONCEPT_FAMILY_OPTIONS


# ----------------------------------------------------------------------
#  Phase 8.4 — Rotation context block
# ----------------------------------------------------------------------


class TestRotationContextBlock:
    def test_first_render_with_no_history_says_so(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "ROTATION CONTEXT" in prompt
        assert "first render in this rotation window" in prompt

    def test_with_history_lists_the_recent_families_in_order(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(),
            recent_concept_families=("offer_driven", "founder_story"),
        )
        assert "ROTATION CONTEXT" in prompt
        # Most-recent → least-recent ordering must surface verbatim.
        idx_offer = prompt.find("Offer Driven")
        idx_founder = prompt.find("Founder Story")
        assert 0 <= idx_offer < idx_founder

    def test_unknown_recent_slugs_are_silently_filtered(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(),
            recent_concept_families=("not_a_family", "social_proof"),
        )
        # The unknown entry must not surface in the rotation block.
        assert "not_a_family" not in prompt
        # The known one must.
        assert "Social Proof" in prompt


# ----------------------------------------------------------------------
#  Phase 8.4 — End-to-end rotation guarantees
# ----------------------------------------------------------------------


class TestEndToEndRotation:
    def test_three_consecutive_renders_have_three_different_families(self):
        # Simulate the caller plumbing rotation history. Three renders,
        # each feeding the previous family back as recent.
        history: list[str] = []
        for _ in range(3):
            prompt = build_image_prompt(
                brief=_brief(goal="Book a table this weekend"),
                profile=_profile(industry="Restaurant"),
                recent_concept_families=tuple(history),
            )
            fam = extract_concept_family(prompt)
            assert fam is not None
            history.insert(0, fam)
        assert len(set(history)) == 3, history

    def test_six_consecutive_renders_have_six_different_families(self):
        # The Phase 8.4 contract is "20 in a row without repeating" —
        # we don't run 20 here (slow), but 6 covers the entire
        # bookings-preferred set and proves the fallback to the wider
        # pool kicks in correctly.
        history: list[str] = []
        for _ in range(6):
            prompt = build_image_prompt(
                brief=_brief(goal="Book a table this weekend"),
                profile=_profile(industry="Restaurant"),
                recent_concept_families=tuple(history),
            )
            fam = extract_concept_family(prompt)
            assert fam is not None
            history.insert(0, fam)
        assert len(set(history)) == 6, history

    def test_explicit_brief_family_overrides_default_pick(self):
        # End-to-end: when the brief sets concept_family, that's what
        # the prompt renders (provided it's not the most-recent).
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
            recent_concept_families=("lifestyle_aspiration",),
        )
        # Lifestyle is recent → picker should NOT pick it.
        fam = extract_concept_family(prompt)
        assert fam != "lifestyle_aspiration"

        prompt2 = build_image_prompt(
            brief={**_brief(goal="Book a table this weekend"), "concept_family": "behind_the_scenes"},
            profile=_profile(industry="Restaurant"),
            recent_concept_families=("lifestyle_aspiration",),
        )
        assert extract_concept_family(prompt2) == "behind_the_scenes"


# ----------------------------------------------------------------------
#  Phase 8.4 — extract_concept_family helper
# ----------------------------------------------------------------------


class TestExtractConceptFamily:
    def test_extracts_from_a_freshly_built_prompt(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert extract_concept_family(prompt) is not None

    def test_returns_none_for_a_pre_84_prompt(self):
        # A prompt without the marker (a legacy stored one) must
        # return None — that's how render.py's rotation query
        # silently skips pre-8.4 history.
        legacy = "Some old prompt text with no marker line at all."
        assert extract_concept_family(legacy) is None

    def test_returns_none_for_empty_input(self):
        assert extract_concept_family("") is None
        assert extract_concept_family(None) is None  # type: ignore[arg-type]

    def test_ignores_marker_with_unknown_slug(self):
        # A prompt that contains the marker pattern but with an
        # unknown slug must be treated as "no concept family" so a
        # stale stored value can't lock out the picker.
        contaminated = "...\nCONCEPT FAMILY — not_a_real_family\n..."
        assert extract_concept_family(contaminated) is None

    def test_extracts_correct_slug_when_present_in_freeform_text(self):
        sample = (
            "...some preamble...\n"
            "CONCEPT FAMILY — authority_positioning\n"
            "...more lines..."
        )
        assert extract_concept_family(sample) == "authority_positioning"


# ----------------------------------------------------------------------
#  Phase 8.4 — Six-test conversion gate (adds CREATIVE UNIQUENESS)
# ----------------------------------------------------------------------


class TestSixTestConversionGate:
    def test_gate_block_states_all_six_tests_must_pass(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "ALL SIX" in prompt

    def test_creative_uniqueness_test_present(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "CREATIVE UNIQUENESS TEST" in prompt
        # The Phase 8.4 brief's specific 60% overlap threshold.
        assert "60%" in prompt

    def test_scroll_stop_test_uses_phase_84_wording(self):
        # Phase 8.4 sharpens the SCROLL-STOP test: show the image for
        # ONE second, ask "what is happening?" — if unclear, reject.
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        assert "ONE second" in prompt
        assert "what is happening" in prompt.lower()

    def test_critical_block_references_six_tests(self):
        prompt = build_image_prompt(brief=_brief(), profile=_profile())
        tail = prompt[-2500:]
        assert "ALL SIX" in tail
        assert "CREATIVE UNIQUENESS" in tail.upper()


# ----------------------------------------------------------------------
#  Phase 8.4 — Critical-block carries concept family + rotation reminder
# ----------------------------------------------------------------------


class TestCriticalCarriesConceptFamily:
    def test_critical_names_the_chosen_concept_family(self):
        prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
        )
        tail = prompt[-2500:]
        # The CRITICAL block reminds the model what family this render
        # must deliver — both human label and slug.
        chosen = extract_concept_family(prompt)
        assert chosen is not None
        assert _CONCEPT_FAMILY_LABELS[chosen] in tail
        assert chosen in tail

    def test_critical_reminds_of_rotation_when_history_was_passed(self):
        prompt = build_image_prompt(
            brief=_brief(),
            profile=_profile(),
            recent_concept_families=("offer_driven",),
        )
        tail = prompt[-2500:]
        # The fatigue-avoidance reminder must be in the closing block.
        assert "20 ads in a row" in tail or "feed-fatigue" in tail.lower()
