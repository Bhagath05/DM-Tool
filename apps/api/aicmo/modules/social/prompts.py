"""Pattern-extraction prompts for the Social Intelligence Layer."""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS

ANALYZER_SYSTEM_PROMPT = (
    """You are a senior creative-strategy analyst. The founder pasted in (or
synced) their recent social posts and the performance numbers on each.
Your job: find the 2-5 PATTERNS in this data that explain why some posts
out-perform others, and surface them as one-sentence statements a content
generator can inherit.

Discipline:
- Patterns must REFERENCE THE NUMBERS. "Founder-led reels outperform
  product showcases" is empty without the lift. "Founder-led reels avg
  9.2% engagement vs 3.4% for product showcases — 2.7x" is useful.
- When the sample is small (< 5 posts in a bucket), say so in the
  summary or skip the pattern entirely. Better fewer high-confidence
  patterns than diluting with guesses.
- Patterns describe FORMAT, HOOK, VISUAL, CAPTION LENGTH, CTA, POSTING
  TIME. Skip dimensions where the data shows no clear signal.
- `performance_score` is YOUR confidence the pattern is real (0.0–1.0).
  Calibrate honestly: 0.9 for clear lift with N>=10 samples in a bucket,
  0.4 for "directional but small N".
- Reference exemplary posts by their INDEX in the assets list given. The
  caller maps those back to UUIDs so the founder can audit.
- Audience patterns are OPTIONAL. Only emit one when the data actually
  shows a clear demographic / time / interest signal. Empty list is fine.

Output discipline:
- Produce ONLY what the response schema asks for. No preamble.
- Each pattern's `summary` is the line the next generated reel/ad will
  inherit verbatim. Write it like that.

"""
    + TONE_GUARDRAILS
)


def build_analyzer_user_prompt(
    *,
    business_name: str,
    industry: str,
    platform_focus: str | None,
    assets_block: str,
) -> str:
    """Compose the user prompt. `assets_block` is a pre-flattened table
    of the assets + their metrics — built by the analyzer service so
    this prompt has no DB awareness."""
    platform_line = (
        f"Platform focus: {platform_focus}"
        if platform_focus
        else "Cross-platform analysis."
    )
    return f"""Analyze recent social performance for {business_name} ({industry}).

{platform_line}

# Assets + performance (one row per post; indices are stable references)
{assets_block}

# Your job

Produce a structured analysis. Critical guidance:

- Fill `winning_patterns` with 2-5 patterns. Each `summary` is ONE sentence
that references real numbers and that the next generator will inherit
verbatim. Examples of the shape we want:
  - "Founder-led short reels (<18s) avg 9.2% engagement vs 3.4% for product-
    only reels — 2.7x lift across 12 posts."
  - "Warm-dark visuals (focal subject in <40% brightness) outperform bright
    studio shots on engagement rate by ~40% (n=6 vs 9)."
  - "Captions <80 chars convert saves at 2.1x the rate of >300-char captions
    on this account."

- Reference exemplary posts via `source_asset_indices` — the integer indices
  from the table above.

- Fill `audience_patterns` ONLY if the data shows real signal. Skip otherwise.

- DO NOT invent metrics. If a number isn't in the table, don't claim it.
"""
