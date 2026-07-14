"""Phase 8 Brand Brain — the identity fields must reach every generator.

`render_context_block` is prepended to every generator's prompt, so it is
the single place that proves the Brand Brain actually flows into AI
generation. These tests pin that the new identity fields render (and degrade
gracefully when unset).
"""

from __future__ import annotations

from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext


def _ctx(**over) -> GenerationContext:
    base = dict(
        user_id="u1",
        business_name="Bella's Bakery",
        industry="Bakery",
        target_audience="Local families who love fresh bread",
        brand_tone="warm",
        generated_at="2026-07-14T00:00:00Z",
    )
    base.update(over)
    return GenerationContext(**base)


def test_brand_identity_renders_when_set() -> None:
    block = render_context_block(
        _ctx(
            brand_colors=["#8B4513", "#F5DEB3"],
            fonts=["Playfair Display", "Inter"],
            keywords=["artisan", "sourdough", "local"],
            brand_rules=["Never use the word 'cheap'", "Always mention same-day baking"],
            writing_style="Short, warm, sensory sentences.",
        )
    )
    assert "# Brand identity" in block
    assert "#8B4513" in block and "#F5DEB3" in block
    assert "Playfair Display" in block
    assert "artisan" in block
    assert "Never use the word 'cheap'" in block
    assert "Short, warm, sensory sentences." in block
    # The inheritance rule must forbid violating a brand rule.
    assert "NEVER violate a brand rule" in block


def test_brand_identity_degrades_gracefully_when_unset() -> None:
    block = render_context_block(_ctx())
    # Section still present, but marked unset rather than ragged/blank.
    assert "# Brand identity" in block
    assert "Brand colours: (not set)" in block
    assert "Writing style: (follow brand tone)" in block
    assert "(none set)" in block  # brand rules empty


def test_keywords_are_capped_to_twelve() -> None:
    block = render_context_block(
        _ctx(keywords=[f"kw{i}" for i in range(20)])
    )
    assert "kw0" in block and "kw11" in block
    assert "kw12" not in block  # capped so the prompt stays compact
