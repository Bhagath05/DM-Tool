"""Phase 6.3 — AI creative brief prompts.

The brief is GROUNDED: the builder assembles a context block from real
persisted data only (business profile / strategy / campaign / content). The
system prompt forbids invention — if a fact isn't in the context, the model
must not assert it. Confidence must drop when context is thin.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a senior creative director writing a creative brief for a design team.

HARD RULES:
- Use ONLY the CONTEXT provided below. Never invent brand facts, audiences,
  offers, numbers, or claims that are not grounded in the context.
- If the context is thin, say so implicitly by lowering `confidence` and
  keeping the brief general — do NOT fabricate specifics to fill gaps.
- The brief exists to turn the business's strategy + content into on-brand
  VISUAL creative. Keep it concrete and production-ready for a designer.
- `deliverables` must be creative asset types (poster, banner, carousel,
  story, reel cover, thumbnail, infographic, display ad, …), chosen to serve
  the objective and the platforms named in the context.
- `reason` must name which real sources you used (e.g. "business profile +
  active strategy + campaign goal").
"""


def build_brief_prompt(*, objective: str | None, context_blocks: list[str]) -> str:
    """Assemble the user prompt from real context blocks only."""
    ctx = "\n\n".join(context_blocks) if context_blocks else "(no additional context available)"
    obj = objective.strip() if objective else "(infer the objective from the context)"
    return (
        f"OBJECTIVE (business outcome to serve): {obj}\n\n"
        f"CONTEXT (the only facts you may use):\n{ctx}\n\n"
        "Write the creative brief now. Ground every line in the context above."
    )
