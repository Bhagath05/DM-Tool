"""Third-party-media provider abstractions.

Mirrors the `llm/providers/` shape — one abstract base per media class,
one concrete impl per provider. Feature modules import these, never the
provider SDK directly. Lets us swap providers (or add a second one) in
~80 LOC of new code without touching callers.

Today: just images/openai. Tomorrow (only when proven needed): images/flux,
videos/runway, voice/elevenlabs, etc.
"""
