"""Typed contracts for the read-only agent runtime.

The LLM produces STRUCTURED DATA (AgentPlan, AgentSynthesis) — never executable
code, function references, or tenant/authorization data. Tool names in a plan
resolve exclusively through the Phase-1 registry allowlist.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceStatus = Literal["ok", "INSUFFICIENT_EVIDENCE"]
AgentMessageRole = Literal["user", "assistant", "tool", "system"]


# --- LLM planning output ----------------------------------------------------
class ProposedToolCall(BaseModel):
    """A tool the model proposes to consult. ``tool_name`` is validated against
    the registry allowlist; ``arguments`` are validated against the tool's own
    input schema. It CANNOT carry a tenant/brand id, a callable, code, a URL, or
    a raw query — those are rejected downstream."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(max_length=64)
    arguments: dict = Field(default_factory=dict)
    purpose: str = Field(default="", max_length=280)


class AgentPlan(BaseModel):
    """The model's structured plan for answering the user."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="", max_length=280)
    answer_strategy: str = Field(default="", max_length=560)
    tool_calls: list[ProposedToolCall] = Field(default_factory=list)
    confidence: int = Field(default=0, ge=0, le=100)
    needs_more_evidence: bool = False


# --- LLM synthesis output ---------------------------------------------------
class AgentSynthesis(BaseModel):
    """The model's grounded answer, produced from tool results treated as data."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(max_length=6000)
    evidence_status: EvidenceStatus = "INSUFFICIENT_EVIDENCE"
    confidence: int = Field(default=0, ge=0, le=100)
    key_observations: list[str] = Field(default_factory=list)
    uncertainty: str = Field(default="", max_length=560)


# --- assembled response types ----------------------------------------------
class EvidenceRef(BaseModel):
    """A safe, non-fabricated pointer to something the agent consulted."""

    label: str
    source: str | None = None
    confidence: int | None = None
    status: str | None = None


class BlockedAction(BaseModel):
    """A non-READ tool the model proposed but the runtime refused to execute."""

    tool_name: str
    operation_class: str
    reason: str = "ACTION_REQUIRES_APPROVAL"


class ReasoningSummary(BaseModel):
    """A SAFE 'why' trace — NOT a chain-of-thought transcript. It records what
    was consulted and concluded, never internal model reasoning tokens."""

    intent: str = ""
    tools_consulted: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    key_observations: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    conclusion: str = ""


class AgentResponse(BaseModel):
    """The typed API response for one agent turn."""

    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    evidence_status: EvidenceStatus
    confidence: int
    tools_consulted: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    actions_blocked: list[BlockedAction] = Field(default_factory=list)
    reasoning_summary: ReasoningSummary


# --- API request/response DTOs ---------------------------------------------
class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: AgentMessageRole
    content: str
    seq: int
    created_at: datetime
    meta: dict = Field(default_factory=dict)


class MessageListResponse(BaseModel):
    conversation_id: uuid.UUID
    items: list[MessageResponse]
