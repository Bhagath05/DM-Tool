"""Business Brain API / domain schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from aicmo.security.prompt_safety import sanitize_prompt_input

EvidenceKind = Literal["fact", "observation", "hypothesis", "recommendation"]
EvidenceCategory = Literal["business", "audience", "market", "marketing"]
ResearchStatus = Literal["queued", "running", "completed", "partial", "failed"]
ErrorCategory = Literal[
    "NOT_CONFIGURED",
    "UNSAFE_URL",
    "RESEARCH_FAILED",
    "PARTIAL_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
    "PROVIDER_UNAVAILABLE",
]
IcpStatus = Literal["hypothesis", "accepted", "rejected", "archived"]


class StartWebsiteResearchRequest(BaseModel):
    website_url: str = Field(min_length=3, max_length=500)

    @field_validator("website_url", mode="before")
    @classmethod
    def _scrub(cls, v: object) -> object:
        if isinstance(v, str):
            return sanitize_prompt_input(v.strip(), field_name="website_url")
        return v


class ResearchJobStartResponse(BaseModel):
    id: uuid.UUID
    status: ResearchStatus
    reused_existing: bool = False


class ResearchJobResponse(BaseModel):
    id: uuid.UUID
    kind: str
    input_url: str
    normalized_url: str
    status: ResearchStatus
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    provider: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    source_count: int = 0
    evidence_count: int = 0
    created_at: datetime
    updated_at: datetime


class EvidenceItem(BaseModel):
    id: uuid.UUID
    kind: EvidenceKind
    category: EvidenceCategory
    claim: str
    confidence: int
    status: str
    claim_key: str | None = None
    superseded_by_id: uuid.UUID | None = None
    source_url: str | None = None
    source_type: str
    snippet: str | None = None
    research_job_id: uuid.UUID | None = None
    discovered_at: datetime
    retrieved_at: datetime | None = None  # alias of discovered_at for agent tools
    created_at: datetime


class EvidenceListResponse(BaseModel):
    items: list[EvidenceItem]
    known_count: int
    unknown_categories: list[str]


class BrainSummaryResponse(BaseModel):
    """What we know / don't know — honest, no fabricated fills."""

    profile_present: bool
    business_name: str | None = None
    website: str | None = None
    industry: str | None = None
    known: list[str]
    unknown: list[str]
    evidence_counts: dict[str, int]
    latest_job: ResearchJobResponse | None = None
    latest_website_job: ResearchJobResponse | None = None
    latest_competitor_job: ResearchJobResponse | None = None
    latest_market_job: ResearchJobResponse | None = None
    icp_count: int = 0
    competitor_candidate_count: int = 0
    market_signal_count: int = 0
    limitations: list[str] = Field(default_factory=list)


class IcpItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    industries: list[str]
    company_size: str | None = None
    geography: list[str]
    buyer_roles: list[str]
    pain_points: list[str]
    buying_signals: list[str]
    exclusions: list[str]
    confidence: int
    status: IcpStatus
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


class IcpListResponse(BaseModel):
    items: list[IcpItem]
    status: Literal["ok", "INSUFFICIENT_EVIDENCE"]
    message: str | None = None


class IcpGenerateResponse(BaseModel):
    items: list[IcpItem]
    status: Literal["ok", "INSUFFICIENT_EVIDENCE"]
    message: str | None = None


# --- Competitor / market research ---

CompetitorCandidateStatus = Literal["candidate", "supported", "rejected", "unknown"]
MarketSignalKind = Literal[
    "category",
    "positioning",
    "demand",
    "pain_point",
    "trend",
    "alternative",
    "competitor_positioning",
]


class StartCompetitorResearchRequest(BaseModel):
    """Optional competitor URLs only — never invent names from thin air.

    If empty, the local provider uses existing website evidence only and may
    return INSUFFICIENT_EVIDENCE.
    """

    competitor_urls: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("competitor_urls", mode="before")
    @classmethod
    def _scrub_urls(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        out: list[str] = []
        for item in v[:5]:
            if isinstance(item, str) and item.strip():
                cleaned = sanitize_prompt_input(
                    item.strip(), field_name="competitor_url"
                )
                if cleaned:
                    out.append(cleaned)
        return out


class StartMarketResearchRequest(BaseModel):
    """Market research uses brand website/profile context — no free-text invent."""

    model_config = {"extra": "forbid"}


class CompetitorCandidate(BaseModel):
    name: str
    reason: str
    source_url: str | None = None
    confidence: int = Field(ge=0, le=100)
    status: CompetitorCandidateStatus = "candidate"
    evidence_kinds: list[EvidenceKind] = Field(default_factory=list)


class MarketSignal(BaseModel):
    signal_kind: MarketSignalKind
    claim: str
    evidence_kind: EvidenceKind
    confidence: int = Field(ge=0, le=100)
    source_url: str | None = None
    source_type: str = "website"


class CompetitorResearchResponse(BaseModel):
    status: Literal[
        "ok",
        "INSUFFICIENT_EVIDENCE",
        "NOT_CONFIGURED",
        "PROVIDER_UNAVAILABLE",
        "running",
        "queued",
        "failed",
    ]
    message: str | None = None
    latest_job: ResearchJobResponse | None = None
    candidates: list[CompetitorCandidate] = Field(default_factory=list)


class MarketResearchResponse(BaseModel):
    status: Literal[
        "ok",
        "INSUFFICIENT_EVIDENCE",
        "NOT_CONFIGURED",
        "PROVIDER_UNAVAILABLE",
        "running",
        "queued",
        "failed",
    ]
    message: str | None = None
    latest_job: ResearchJobResponse | None = None
    signals: list[MarketSignal] = Field(default_factory=list)


# --- Provider seam (not persisted as-is) ---


class EvidenceCandidate(BaseModel):
    kind: EvidenceKind
    category: EvidenceCategory
    claim: str = Field(min_length=3, max_length=1000)
    confidence: int = Field(ge=0, le=100)
    source_url: str | None = None
    source_type: str = "website"
    snippet: str | None = Field(default=None, max_length=800)
    claim_key: str | None = Field(default=None, max_length=160)


class ResearchResult(BaseModel):
    """Output of a research provider — never invent when empty."""

    status: Literal["completed", "partial", "failed"]
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    provider: str
    final_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    # Structured payload stored on the job (competitors / market), not CRM rows.
    result_summary: dict | None = None


class CompetitorResearchResult(ResearchResult):
    """Typed alias — same shape, provider-specific semantics."""


class MarketResearchResult(ResearchResult):
    """Typed alias — same shape, provider-specific semantics."""
