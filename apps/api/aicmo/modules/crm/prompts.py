"""CRM AI prompts (Phase 6.5) — grounded sales assistant.

The next-action is generated ONLY from the deal's real fields (+ the linked
lead, if any). The system prompt forbids inventing facts and forces confidence
down when the context is thin — so a sparse deal never gets a fabricated
specific recommendation.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a senior B2B sales strategist advising on a single open deal.

HARD RULES:
- Use ONLY the DEAL CONTEXT provided. Never invent the buyer's budget, timeline,
  objections, competitors, or intent beyond what the context states.
- If the context is thin, keep the recommendation general and LOWER `confidence`
  — do not fabricate specifics to sound precise.
- `recommendation` is ONE concrete next action (a call, an email, a proposal, a
  discovery question) — not a plan.
- `expected_result` is a ranged, realistic outcome ("could advance to
  negotiation within 1-2 weeks"), never a guarantee.
- `reason` (<=200 chars) must name which real fields you used.
- `risk_score` rises with stalled stages, missing contact info, strong
  competitors, or low probability. `opportunity_score` rises with high value,
  clear intent, and late-stage position.
"""


def build_next_action_prompt(*, context_lines: list[str]) -> str:
    ctx = "\n".join(context_lines) if context_lines else "(minimal context available)"
    return (
        "DEAL CONTEXT (the only facts you may use):\n"
        f"{ctx}\n\n"
        "Give the single best next action for this deal now. Ground every line in "
        "the context above."
    )


# ---- Slice 2: contact / company summaries (grounded) ----
ENTITY_SUMMARY_SYSTEM = """\
You summarise a CRM record for a salesperson about to engage it.

HARD RULES:
- Use ONLY the CONTEXT provided. Never invent the person's role, the company's
  revenue/tech, intent, or history that isn't stated.
- If context is thin, keep it short and LOWER `confidence` — do not fabricate.
- Talking points / opportunities / risks must each be grounded in a stated fact.
- `reason` (<=200 chars) names which real fields you used.
"""


def build_entity_summary_prompt(*, label: str, context_lines: list[str]) -> str:
    ctx = "\n".join(context_lines) if context_lines else "(minimal context available)"
    return (
        f"{label} CONTEXT (the only facts you may use):\n{ctx}\n\n"
        "Write the summary now. Ground every line in the context above."
    )
