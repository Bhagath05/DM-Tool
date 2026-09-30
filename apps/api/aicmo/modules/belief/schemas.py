"""Typed DTOs for the belief memory service + resolver.

Inputs are server-facing (called by domain services, never exposed to the LLM as
a write path). They deliberately carry NO tenant/organization/brand id — scope is
taken from the server-side TenantContext. ``extra="forbid"`` blocks smuggled
authorization fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.belief.enums import (
    BeliefCategory,
    BeliefStatus,
    EvidenceRefKind,
    EvidenceRelation,
)


class EvidenceRefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: EvidenceRefKind
    ref_id: uuid.UUID | None = None  # required for DB-backed kinds; None for data_source
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS
    note: str | None = Field(default=None, max_length=280)


class BeliefCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: BeliefCategory
    subject_key: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=2000)
    scope: dict = Field(default_factory=dict)
    evidence: list[EvidenceRefInput] = Field(default_factory=list)


class EvidenceRefView(BaseModel):
    ref_kind: EvidenceRefKind
    ref_id: uuid.UUID | None
    relation: EvidenceRelation
    note: str | None = None


class BeliefView(BaseModel):
    id: uuid.UUID
    category: BeliefCategory
    subject_key: str
    statement: str
    scope: dict
    status: BeliefStatus
    confidence: int
    confidence_reason: str
    evidence_count: int
    validated_at: datetime | None
    valid_from: datetime
    valid_until: datetime | None
    superseded_by_id: uuid.UUID | None
    parent_belief_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRefView] = Field(default_factory=list)


class BeliefResolution(BaseModel):
    """A bounded, deterministic snapshot for the future agent to reason over."""

    brand_id: uuid.UUID
    active: list[BeliefView] = Field(default_factory=list)
    superseded: list[BeliefView] = Field(default_factory=list)
    contradicted: list[BeliefView] = Field(default_factory=list)
    truncated: bool = False
