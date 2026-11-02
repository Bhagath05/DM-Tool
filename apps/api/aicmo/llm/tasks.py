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
    "agent_plan",
    "agent_summarize",
]

KNOWN_LLM_TASKS: frozenset[str] = frozenset(
    {
        "business_research",
        "strategy_reasoning",
        "creative_generation",
        "intelligence",
        "agent_reasoning",
        "agent_plan",
        "agent_summarize",
    }
)

ALLOWED_LLM_PROVIDERS: frozenset[str] = frozenset(
    {"anthropic", "openai", "google", "ollama"}
)

# Phase 7.19 — tasks eligible for LOCAL Ollama routing. Deliberately a small,
# code-reviewed allowlist of lower-stakes generative tasks. High-stakes reasoning
# (strategy_reasoning, intelligence, agent_plan, agent_reasoning) must stay on an
# external provider; routing any task outside this set to ollama fails closed in
# the router. This is a capability/safety gate, not a routing default — operators
# still opt in per task via LLM_TASK_MODELS.
OLLAMA_ELIGIBLE_TASKS: frozenset[str] = frozenset(
    {
        "creative_generation",
        "agent_summarize",
        "business_research",
    }
)
