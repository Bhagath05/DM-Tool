"""Tests for LLM output normalization before strict schema validation."""

from __future__ import annotations

from aicmo.modules.content.normalize import normalize_content_payload


def test_carousel_fills_missing_slide_title_from_body() -> None:
    out = normalize_content_payload(
        "carousel",
        {
            "slides": [
                {"body": "Check your CAS documents before applying."},
                {"title": "Visa timeline", "body": "Apply 90 days before intake."},
            ]
        },
    )
    assert out["slides"][0]["title"] == "Check your CAS documents before applying"
    assert out["slides"][1]["title"] == "Visa timeline"


def test_carousel_synthesizes_cta_slide_from_last_slide() -> None:
    out = normalize_content_payload(
        "carousel",
        {
            "slides": [
                {"title": "Step 1", "body": "Gather transcripts."},
                {"title": "Book now", "body": "Free counselling this week."},
            ],
            "cta": "Book free session",
        },
    )
    assert out["cta_slide"]["title"] == "Book now"
    assert out["cta_slide"]["body"] == "Free counselling this week."


def test_reel_trims_on_screen_text_to_eight() -> None:
    out = normalize_content_payload(
        "reel",
        {"on_screen_text": [f"line {i}" for i in range(12)]},
    )
    assert len(out["on_screen_text"]) == 8
    assert out["on_screen_text"][0] == "line 0"


def test_reel_synthesizes_voiceover_from_hook_beats_and_cta() -> None:
    out = normalize_content_payload(
        "reel",
        {
            "hook": "Stop guessing your Canada pathway.",
            "beats": [
                {"description": "Compare PNP vs Express Entry on screen."},
                {"description": "Show IELTS 6.5 eligibility checklist."},
            ],
            "cta": "Book a free counselling call.",
        },
    )
    vo = out["voiceover_script"]
    assert "Stop guessing your Canada pathway." in vo
    assert "Compare PNP vs Express Entry on screen." in vo
    assert "Book a free counselling call." in vo


def test_carousel_normalizes_cta_slide_missing_title() -> None:
    out = normalize_content_payload(
        "carousel",
        {
            "slides": [{"title": "Step 1", "body": "Gather transcripts."}],
            "cta_slide": {"body": "Are you ready to book your free counselling session?"},
            "cta": "Book free session",
        },
    )
    assert out["cta_slide"]["title"] == "Are you ready to book your free counselling session?"
    assert out["cta_slide"]["body"] == "Are you ready to book your free counselling session?"


def test_reel_fills_missing_beat_labels() -> None:
    out = normalize_content_payload(
        "reel",
        {"beats": [{"description": "Opening shot of campus."}, {"label": "Payoff", "description": "CTA end card."}]},
    )
    assert out["beats"][0]["label"] == "Scene 1"
    assert out["beats"][1]["label"] == "Payoff"


def test_landing_page_fills_missing_benefit_titles() -> None:
    out = normalize_content_payload(
        "landing_page_copy",
        {
            "benefits": [
                {"body": "Get personalized university shortlists for your career goals."},
                {"title": "Visa support", "body": "Step-by-step document checklist."},
            ]
        },
    )
    assert out["benefits"][0]["title"] == "Get personalized university shortlists for your career goals"
    assert out["benefits"][1]["title"] == "Visa support"
