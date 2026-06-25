"""Generator hint normalization — must survive LLM omissions."""

from __future__ import annotations

from aicmo.modules.advisor.intelligence import _normalize_generator_hint


def test_normalize_returns_defaults_when_llm_omits_hint() -> None:
    hint = _normalize_generator_hint(None, default_target="content")
    assert hint["target"] == "content"
    assert hint["format"] == "carousel"
    assert hint["goal"]


def test_normalize_ad_target_defaults_to_instagram_promo() -> None:
    hint = _normalize_generator_hint(None, default_target="ad")
    assert hint["target"] == "ad"
    assert hint["format"] == "instagram_promo"
