"""AI Sales Assistant schemas (Phase 6.5, Slice 5).

`SalesInsight` is the structured LLM output — every field grounded in real CRM
data (the system prompt forbids invention). `InsightResponse` is the persisted
evidence-contract envelope the API returns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SubjectType = Literal["lead", "deal", "contact", "company", "task", "email"]

# The insight "kinds" the assistant can produce (validated per subject type).
InsightKind = Literal[
    "lead_intelligence",
    "deal_intelligence", "deal_prediction", "deal_coaching",
    "contact_intelligence",
    "company_intelligence",
    "meeting_intelligence",
    "call_intelligence",
    "email_intelligence",
    "automation_suggestions",
]


class Evidence(BaseModel):
    source: str = Field(description="Which real CRM record/field this came from.")
    detail: str = Field(description="The specific fact drawn from that source.")


class SalesInsight(BaseModel):
    """What the LLM produces — the recommendation contract. Every list item must
    trace to a real data point supplied in the context."""

    summary: str = Field(description="What the data shows about this record right now.")
    recommendation: str = Field(description="The single best next action.")
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    reasoning: str = Field(description="Why the recommendation follows from the evidence.")
    confidence: int = Field(ge=0, le=100)
    affected_records: list[str] = Field(
        default_factory=list, max_length=12,
        description="Records this touches, e.g. 'deal: Acme renewal', 'contact: Jane'.",
    )
    expected_outcome: str = Field(description="Ranged, realistic outcome if acted on.")


class GenerateInsightRequest(BaseModel):
    kind: InsightKind | None = None  # default is chosen per subject type
    force: bool = False  # regenerate even if a fresh cached insight exists


class InsightResponse(BaseModel):
    """The persisted evidence-contract envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    kind: str
    summary: str | None
    recommendation: str | None
    evidence: list
    reasoning: str | None
    confidence: int
    affected_records: list
    expected_outcome: str | None
    insufficient_evidence: bool
    model: str | None
    generated_at: datetime
    expires_at: datetime | None


class InsightList(BaseModel):
    items: list[InsightResponse]
