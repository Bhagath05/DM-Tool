"""Canonical LLM task identifiers.

Product code selects a *task*; the policy layer maps task → provider/model.
Callers must not invent free-form task strings for routing — only members of
`LLMTask` / `KNOWN_LLM_TASKS` are accepted.
"""

from __future__ import annotations

from typing import Literal

LLMTask = Literal[
    "business_research",
    "strategy_reasoning",
    "creative_generation",
    "intelligence",
    "agent_reasoning",
]

KNOWN_LLM_TASKS: frozenset[str] = frozenset(
    {
        "business_research",
        "strategy_reasoning",
        "creative_generation",
        "intelligence",
        "agent_reasoning",
    }
)

ALLOWED_LLM_PROVIDERS: frozenset[str] = frozenset({"anthropic", "openai", "google"})
