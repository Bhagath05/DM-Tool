"""Decision Engine schemas.

`DecisionSignals` is the factual snapshot gathered from real app data (no LLM).
`Decision` / `DecisionReport` is the LLM structured output + API response. Every
decision carries evidence + risks + alternatives; the report states how well the
available data grounded it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Urgency = Literal["now", "this_week", "this_month", "monitor"]


class DecisionSignals(BaseModel):
    """A factual snapshot of the workspace — the evidence base. Built purely
    from real queries; the LLM may only cite what appears here."""

    has_profile: bool
    business_name: str | None = None
    industry: str | None = None
    growth_stage: str | None = None
    primary_goal: str | None = None
    goals: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)

    # Analytics / leads
    total_leads: int = 0
    leads_7d: int = 0
    leads_30d: int = 0
    hot_leads: int = 0
    total_views: int = 0
    conversion_rate: float = 0.0
    landing_pages_published: int = 0

    # Performance (paid/creative)
    performance_has_data: bool = False
    performance_rows: int = 0
    creatives_tracked: int = 0
    performance_diagnostics: int = 0

    # Publishing
    scheduled_posts: int = 0
    published_posts: int = 0
    failed_posts: int = 0

    # Strategy
    has_strategy: bool = False
    strategy_top_move: str | None = None

    # Learned memory (reused from the existing Learning Engine — social
    # winning/audience patterns). What has actually worked for this brand.
    winning_patterns: list[str] = Field(default_factory=list)
    audience_patterns: list[str] = Field(default_factory=list)

    # Synthesised cross-domain lessons from the Learning Engine (Module 6),
    # already routed to `decision`. Higher-order than the raw patterns above —
    # durable observations that should steer this decision ("obs → rec").
    learning_insights: list[str] = Field(default_factory=list)

    # The brand's active business goals + real progress (Phase 4.3). Decisions
    # should serve these; empty when none are set.
    business_goals: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """One structured decision — never an executed action."""

    decision: str = Field(description="The decision itself, one plain line (e.g. 'Shift focus to Instagram this week').")
    reasoning: str = Field(description="Why — the logic connecting the evidence to the decision.")
    evidence: list[str] = Field(description="The specific real signals this stands on (quote the numbers/facts from the snapshot). If evidence is thin, say so here.")
    expected_impact: str = Field(description="Plain-language outcome if acted on — always a range, never a single magic number.")
    confidence: int = Field(ge=0, le=100)
    urgency: Urgency
    recommended_action: str = Field(description="The single recommended next step (a human does it — nothing auto-runs).")
    alternative_actions: list[str] = Field(default_factory=list, description="Other viable options.")
    risks: list[str] = Field(default_factory=list, description="What could go wrong / what to watch.")
    business_objective: str = Field(description="Which of the business's goals this decision serves.")
    affected_channels: list[str] = Field(default_factory=list, description="Channels this touches (e.g. instagram, email, ads).")


class DecisionReport(BaseModel):
    decisions: list[Decision] = Field(description="Prioritised decisions grounded in the signals. Fewer, well-evidenced decisions beat many weak ones.")
    data_sufficiency: str = Field(description="Honest one-paragraph note on how much real data was available and what's missing to decide better.")


class DecisionReportResponse(BaseModel):
    report: DecisionReport
    signals: DecisionSignals  # the evidence base, returned so the UI can show it
