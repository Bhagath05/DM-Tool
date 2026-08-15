"""Regression: an over-length creative_brief.cta is fitted, not rejected.

OpenAI structured outputs do not enforce string maxLength, so GPT can return a
`creative_brief.cta` longer than the 80-char brief contract. The brief must fit
it deterministically (at a word boundary) so downstream SocialPostFull
validation succeeds instead of raising `string_too_long`.
"""

from __future__ import annotations

from aicmo.copy.creative_brief import MarketingCreativeBrief
from aicmo.modules.content.schemas import SocialPostFull


def _brief_kwargs(**overrides) -> dict:
    base = dict(
        objective="Increase qualified demo bookings from local clinics this month.",
        audience="Clinic owners in Austin evaluating patient-intake software, ready to buy.",
        hook="Your front desk is drowning in no-shows — here's the 20-second fix.",
        offer="Free 14-day trial plus done-for-you setup, no card required.",
        cta="Book a free demo",
        visual_direction="Bright clinic reception, friendly staff, phone showing the app UI.",
        platform="Instagram feed 4:5",
    )
    base.update(overrides)
    return base


def test_cta_within_limit_is_unchanged() -> None:
    brief = MarketingCreativeBrief(**_brief_kwargs(cta="Book your free demo today"))
    assert brief.cta == "Book your free demo today"


def test_overlong_cta_is_fitted_to_word_boundary_not_rejected() -> None:
    long_cta = (
        "Book your free 30-minute strategy consultation with our senior growth "
        "experts today and start scaling immediately"
    )
    assert len(long_cta) > 80

    brief = MarketingCreativeBrief(**_brief_kwargs(cta=long_cta))

    assert len(brief.cta) <= 80
    assert brief.cta  # non-empty, still meaningful
    assert long_cta.startswith(brief.cta)  # left-prefix trim, never mid-content
    assert not brief.cta.endswith(" ")  # no trailing whitespace


def test_overlong_single_token_cta_is_hard_capped() -> None:
    # No word boundary available -> must still be <=80 and valid, not raise.
    brief = MarketingCreativeBrief(**_brief_kwargs(cta="x" * 200))
    assert len(brief.cta) <= 80


def test_social_post_full_accepts_overlong_brief_cta() -> None:
    """Production path: OpenAI payload → SocialPostFull.model_validate(...)."""
    long_cta = (
        "Book your free 30-minute strategy consultation with our senior growth "
        "experts today and start scaling immediately"
    )
    published_cta = "Book a free demo"
    payload = {
        "creative_brief": _brief_kwargs(cta=long_cta),
        "strategy": {
            "trend_influence": "none — grounded in profile only",
            "audience_angle": "curiosity",
            "strategy_note": "This works because it is specific and timely for clinics.",
        },
        "hook": "Stop losing patients to no-shows.",
        "body": "Our intake flow cuts front-desk chaos in 20 seconds flat.",
        "hashtags": ["#clinicops", "#healthcare", "#intake"],
        "cta": published_cta,
        "cta_variants": ["See a live walkthrough", "Start your free trial"],
    }

    post = SocialPostFull.model_validate(payload)

    assert len(post.creative_brief.cta) <= 80
    assert post.cta == published_cta  # published CTA is not truncated
