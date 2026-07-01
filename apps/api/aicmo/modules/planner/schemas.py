"""Daily-plan schemas. `DailyPlan` is the LLM structured output + API response.

Every task explains WHY (grounded in the strategy/profile) and names a
`suggested_action` surface — but the planner NEVER executes anything.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TaskCategory = Literal[
    "content",
    "social",
    "ads",
    "seo",
    "email",
    "leads",
    "landing_page",
    "research",
    "other",
]
Priority = Literal["high", "medium", "low"]
Effort = Literal["quick", "medium", "deep"]


class PlannedTask(BaseModel):
    """One concrete thing to do today."""

    title: str = Field(description="The task as an imperative, plain-language line, e.g. 'Post a 60-second reel about your cold brew'.")
    category: TaskCategory
    why: str = Field(description="Why this matters today — tie it to the strategy or a real signal. No fabricated numbers.")
    priority: Priority
    effort: Effort = Field(description="Rough effort: quick (<15 min), medium (~1h), deep (half-day+).")
    suggested_action: str = Field(description="Where a human would do this (e.g. 'Content Studio → reel', 'Leads → follow up'). Naming only — the planner never executes it.")


class DailyPlan(BaseModel):
    """Today's plan — a short, prioritized, grounded task list."""

    summary: str = Field(description="One line: what today is about, in plain language.")
    focus: str = Field(description="The single most important outcome to move today.")
    tasks: list[PlannedTask] = Field(description="3-7 concrete tasks for today, ordered by priority. Never more than 7 — a founder can't do more.")


class DailyPlanResponse(BaseModel):
    plan: DailyPlan
    # True when a marketing strategy grounded the plan; False when we planned
    # from the profile alone (so the UI can nudge 'generate a strategy').
    grounded_in_strategy: bool
