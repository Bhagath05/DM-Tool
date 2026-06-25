"""Centralised banned-phrase + tone enforcement.

The platform-wide voice target: **smart operator**. Not startup-guru, not
LinkedIn-bro, not AI-assistant, not corporate boilerplate.

Every generator prompt imports `TONE_GUARDRAILS` and pastes it into the
system message. That's how we keep voice consistent across content / ads /
visuals / campaigns / bundles / coach without 8 copies of the same list.
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------------
#  THE LIST.
#  Add to the right bucket. Never delete the comment justifications.
# ----------------------------------------------------------------------

# Corporate / startup-guru sludge. These make a generator output read like
# a LinkedIn post by someone selling a course.
_CORPORATE_CLICHES: tuple[str, ...] = (
    "revolutionize",
    "revolutionary",
    "game-changing",
    "game-changer",
    "next-level",
    "next generation",
    "cutting-edge",
    "world-class",
    "best-in-class",
    "industry-leading",
    "thought leader",
    "thought leadership",
    "synergy",
    "synergies",
    "leverage",
    "leveraging",
    "maximize",
    "maximise",
    "supercharge",
    "supercharged",
    "skyrocket",
    "10x",
    "transformative",
    "transformational",
    "transform your",
    "elevate your",
    "elevate the",
    "unlock growth",
    "unlock your",
    "unlock the power",
    "harness the power",
    "ai-powered",
    "ai powered",
    "seamless",
    "seamlessly",
    "boost engagement",
    "boost your",
    "going forward",
    "moving forward",
    "circle back",
    "actionable insights",
    "value-add",
    "value add",
    "ecosystem",
    "stakeholder",
    "north star",
    "low-hanging fruit",
    "best practices",
    "deep dive",
    "drill down",
    "move the needle",
    "needle-moving",
)

# Empty / generic CTAs. These appear in ad copy + visual briefs when the
# LLM is being lazy. Banned because they don't tell the visitor anything.
_WEAK_CTAS: tuple[str, ...] = (
    "click here",
    "learn more",
    "find out more",
    "check it out",
    "check this out",
    "discover more",
    "see more",
    "explore more",
    "read more",
    "check the link in bio",
    "link in bio",
    "get started today",
    "sign up now",  # too generic — name the payoff
    "join us",
)

# Fake-urgency / breathless tone. These are the marketing equivalent of
# all-caps. They erode trust because everyone has seen them a million
# times on bad ads.
_HYPE: tuple[str, ...] = (
    "huge",
    "massive",
    "insane",
    "mind-blowing",
    "mindblowing",
    "epic",
    "absolutely amazing",
    "absolutely incredible",
    "you won't believe",
    "this changes everything",
    "literally",  # almost always misused
)

# AI-assistant tells. The model gives itself away with these.
_AI_TELLS: tuple[str, ...] = (
    "as an ai",
    "as a language model",
    "delve into",
    "tapestry of",
    "navigating the",
    "in today's fast-paced",
    "in the realm of",
    "it's important to note",
    "i hope this helps",
    "let me know if",
    "feel free to",
    "certainly!",
    "absolutely!",
    "great question",
)

#: Public banned list — union of the four buckets above. Lowercase.
BANNED_PHRASES: tuple[str, ...] = (
    _CORPORATE_CLICHES + _WEAK_CTAS + _HYPE + _AI_TELLS
)

# Pretty-printed for prompt embedding. Keep under ~400 tokens; the LLM
# only needs a strong nudge, not a wall of text.
_PROMPT_BANNED_LIST = ", ".join(BANNED_PHRASES[:60])


TONE_GUARDRAILS: str = f"""# Platform voice (non-negotiable)
You are writing for a tool that founders trust because it does NOT sound \
like generic AI. Hit this voice on every line:

- **Smart operator**: someone who actually runs ads and writes copy. Calm, \
specific, direct. No exclamation marks unless a real human would use one.
- **Plain English**: short sentences. Concrete nouns. Real verbs. \
Specificity beats cleverness.
- **No hedging**, no apologies, no preamble. Don't say "I hope this helps."

# Banned phrases (do NOT write any of these, including conjugations)
{_PROMPT_BANNED_LIST}

# Banned tone patterns
- No "elevate your X" / "transform your X" / "supercharge your X" \
constructions. Pick a real verb that describes the actual action.
- No "in today's fast-paced world", "in the realm of", "navigating the \
landscape of" — these are AI tells. Skip them entirely.
- No empty CTAs ("click here", "learn more", "discover more"). A good \
CTA names the payoff: "Grab the 7-day plan", "Reserve your tasting".
- No fake urgency ("HUGE", "MASSIVE", "INSANE", "literally"). The reader \
will trust you less if you shout.
- No emoji spam. One emoji per piece is the cap. Zero is usually right.

# Output discipline
If you catch yourself writing one of the banned phrases, rewrite. The \
test: would a sharp founder running ads at a coffee shop actually say \
this out loud?"""


# ----------------------------------------------------------------------
#  Post-generation utilities
# ----------------------------------------------------------------------

# Compiled regex bank — anchored to whole-word boundaries so "leverage"
# matches but "leveraged" inside a longer word doesn't get mangled in
# the middle of unrelated text.
_BANNED_RX = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)


def find_banned_phrases(text: str) -> list[str]:
    """Return all banned phrases that appear in `text`. Useful for logging
    + future evals — we'd rather know which prompts the LLM still leaks
    on than silently scrub everything."""
    if not text:
        return []
    seen: list[str] = []
    for match in _BANNED_RX.finditer(text):
        phrase = match.group(0).lower()
        if phrase not in seen:
            seen.append(phrase)
    return seen


def scrub_text(text: str, *, replacement: str = "—") -> str:
    """Replace banned phrases with `replacement`. Conservative: we only
    use this on FREE-FORM text fields where a banned phrase is genuinely
    a tone failure, not on structured fields where the original wording
    might carry meaning the caller needs.

    Right now no caller uses scrub_text — the strategy is prompt-side
    prevention first. Kept here for the next phase when we add per-field
    cleanup based on real usage data.
    """
    if not text:
        return text
    return _BANNED_RX.sub(replacement, text)


# ----------------------------------------------------------------------
#  Render-prompt sanitiser
# ----------------------------------------------------------------------

# Strip embedded text-overlay instructions from a CTA placement string
# before forwarding to image-gen. Examples we kill:
#   "...positioned bottom-center. Text: 'Discover More'."
#   "...with the label 'Order Now' in bold."
#   '...reading "Shop the drop"'
# This prevents the "DO NOT render text" directive from being contradicted
# inside the brief itself.
_OVERLAY_TEXT_RX = re.compile(
    r"""
    \s*[.,;:]?\s*                              # optional leading punctuation
    (?:                                        # text-introducing phrases:
        text\s*[:=]                            #   "Text:"
        | label(?:\s+is| reading)?\s*[:=]?     #   "Label:" or "Label reading"
        | reading                              #   "reading 'X'"
        | with\s+the\s+(?:text|words?)\s+      #   "with the text 'X'"
        | saying                               #   "saying 'X'"
    )
    \s*                                        # ws
    [\'"‘“]                          # opening quote (straight or curly)
    [^\'"’”]{1,80}                   # the actual overlay text
    [\'"’”]                          # closing quote
    \s*[.,;]?                                  # optional trailing punctuation
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_overlay_text_instructions(text: str) -> str:
    """Remove embedded overlay-text directives from a brief field before
    feeding it to image-gen. Idempotent: running twice is fine."""
    if not text:
        return text
    cleaned = _OVERLAY_TEXT_RX.sub("", text)
    # Collapse double spaces / hanging punctuation left behind.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    return cleaned
