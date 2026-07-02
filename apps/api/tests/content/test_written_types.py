"""Phase 6.2 — written/long-form content types (blog, email, product, PR).

Verifies the new types are fully wired into the EXISTING generation pipeline
(dispatch completeness), that each schema validates + splits correctly, and that
non-platform types skip the social-platform check.
"""

from __future__ import annotations

import pytest

from aicmo.modules.content import prompts, schemas


def test_every_content_type_is_fully_wired():
    # Dispatch completeness: a new type without a schema OR a prompt would
    # 500 at generation. This test fails loudly if wiring is incomplete.
    for ct in schemas.CONTENT_TYPES:
        assert ct in schemas.SCHEMA_BY_TYPE, f"{ct} missing from SCHEMA_BY_TYPE"
        assert ct in prompts._TYPE_INSTRUCTIONS, f"{ct} missing from _TYPE_INSTRUCTIONS"


def test_new_written_types_registered():
    for ct in ("blog_article", "email", "product_description", "press_release"):
        assert ct in schemas.CONTENT_TYPES
        assert ct in schemas.NON_PLATFORM_TYPES


def _brief():
    # MarketingCreativeBrief is required on every schema; build a minimal valid one.
    from aicmo.copy.creative_brief import MarketingCreativeBrief

    fields = MarketingCreativeBrief.model_fields
    sample: dict = {}
    for name, f in fields.items():
        if f.is_required():
            ann = str(f.annotation)
            if "list" in ann:
                sample[name] = ["alpha", "bravo", "charlie"]
            elif "int" in ann or "float" in ann:
                sample[name] = 1
            else:
                # brief fields carry min_length=10 — use a long placeholder.
                sample[name] = f"placeholder {name} value"
    return sample


def _strategy():
    return {
        "trend_influence": "none — grounded in profile only",
        "audience_angle": "curiosity",
        "strategy_note": "This works because it is specific and timely.",
    }


def test_blog_article_schema_validates_and_splits():
    payload = {
        "creative_brief": _brief(),
        "strategy": _strategy(),
        "title": "How to X",
        "slug": "how-to-x",
        "meta_description": "A guide to X for Y.",
        "primary_keyword": "how to x",
        "secondary_keywords": ["x tips"],
        "intro": "Intro para.",
        "sections": [
            {"heading": "One", "body": "Body one."},
            {"heading": "Two", "body": "Body two."},
            {"heading": "Three", "body": "Body three."},
        ],
        "conclusion": "Wrap up.",
        "cta": "Start today.",
        "reading_time_minutes": 5,
    }
    model = schemas.BlogArticleFull.model_validate(payload)
    strategy, output = schemas.split_strategy("blog_article", model)
    assert strategy.audience_angle == "curiosity"
    assert output["title"] == "How to X"
    assert "strategy" not in output  # strategy is popped out


@pytest.mark.parametrize(
    "ct,cls,extra",
    [
        (
            "email",
            "EmailFull",
            {
                "subject_lines": ["A", "B"],
                "preview_text": "hi",
                "greeting": "Hi {{first_name}},",
                "body": "Body.",
                "cta": "Book now.",
                "cta_url_hint": "the booking page",
            },
        ),
        (
            "product_description",
            "ProductDescriptionFull",
            {
                "title": "Widget",
                "tagline": "The best widget.",
                "short_description": "A widget.",
                "long_description": "A very good widget.",
                "key_features": ["fast", "cheap", "durable"],
                "cta": "Add to cart.",
            },
        ),
        (
            "press_release",
            "PressReleaseFull",
            {
                "headline": "Company launches X",
                "subheadline": "A new thing.",
                "dateline": "CITY, State — Month Day, Year",
                "lead_paragraph": "Who what when where why.",
                "body_paragraphs": ["Para one with a quote.", "Para two."],
                "boilerplate": "About the company.",
                "media_contact": "[Name], [email]",
            },
        ),
    ],
)
def test_written_schemas_validate_and_split(ct, cls, extra):
    payload = {"creative_brief": _brief(), "strategy": _strategy(), **extra}
    model = getattr(schemas, cls).model_validate(payload)
    strategy, output = schemas.split_strategy(ct, model)
    assert strategy.strategy_note
    assert "strategy" not in output
    assert "creative_brief" in output


def test_prompt_instructions_are_substantive_for_new_types():
    # Each new type ships a real, non-trivial task instruction (no placeholder).
    for ct in ("blog_article", "email", "product_description", "press_release"):
        instr = prompts._TYPE_INSTRUCTIONS[ct]
        assert isinstance(instr, str) and len(instr) > 80
        # sanity: the instruction is about the right artifact
        assert any(
            kw in instr.lower()
            for kw in ("blog", "email", "product", "press release", "article", "copy")
        )
