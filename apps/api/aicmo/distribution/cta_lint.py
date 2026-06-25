"""Lightweight CTA quality scoring.

Not a hard validator — a soft signal surfaced in the UI so users see when
the model got lazy ("Learn more" / "Click here"). Pure function, no I/O.

Rules (each subtracts from a starting score of 100):
- Below 4 chars OR above 60 chars: -40 (basically unusable)
- Not verb-led: -25 (a CTA without a verb is just a label)
- Contains a banned generic phrase: -30
- Contains a vague call ("more", "info") without a specific noun: -10

Returns 0..100 — higher is better. Anything <60 is worth flagging in the UI.
"""

from __future__ import annotations

import re

# Curated list of common marketing-actionable verbs. Not exhaustive — covers
# the ~95% case. The first word of the CTA is checked against this set.
_VERBS = frozenset(
    {
        "get", "grab", "download", "claim", "unlock", "discover", "see",
        "watch", "join", "start", "try", "book", "schedule", "save",
        "buy", "shop", "order", "subscribe", "sign", "register", "apply",
        "request", "explore", "build", "launch", "create", "design",
        "send", "share", "tag", "comment", "follow", "tap", "swipe",
        "find", "compare", "calculate", "estimate", "check", "test",
        "preview", "snag", "secure", "reserve", "reveal", "uncover",
        "skip", "stop", "fix", "solve", "learn",  # "learn" tolerated alone, penalised if "learn more"
    }
)

# Bottom-of-the-barrel phrases that almost never beat a specific CTA.
_BANNED_PHRASES = (
    "click here",
    "learn more",
    "find out more",
    "read more",
    "more info",
    "check it out",
    "more details",
)

# Words that on their own carry no conversion intent.
_VAGUE_TOKENS = ("more", "info", "details", "stuff", "things")


def score_cta(cta: str) -> int:
    """Return a 0-100 quality score for a CTA string."""
    if not cta or not cta.strip():
        return 0

    text = cta.strip()
    lower = text.lower()
    score = 100

    length = len(text)
    if length < 4 or length > 60:
        score -= 40

    first_word = re.split(r"[\s,.;!?]+", lower, maxsplit=1)[0]
    if first_word not in _VERBS:
        score -= 25

    if any(phrase in lower for phrase in _BANNED_PHRASES):
        score -= 30

    # Vague tokens without a noun-anchor — e.g. "Learn more" loses 30 from
    # the banned phrase AND 10 here.
    tokens = re.findall(r"[a-z']+", lower)
    if any(t in _VAGUE_TOKENS for t in tokens):
        # Only penalise if no specific noun > 4 chars accompanies it.
        nouns = [t for t in tokens if len(t) > 4 and t not in _VAGUE_TOKENS]
        if not nouns:
            score -= 10

    return max(0, min(100, score))
