"""Module 9 — Autonomy Policy schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The governable action types (the user's list). "default" is the catch-all
# fallback bucket.
ActionType = Literal[
    "content_generation",
    "campaign_creation",
    "campaign_launch",
    "social_publishing",
    "email_sending",
    "budget_change",
    "ad_creation",
    "ad_spending",
    "image_generation",
    "ai_recommendation",
    "ai_decision",
    "crm_update",
    "integration",
]

# What the AI is allowed to do for an action type.
PolicyMode = Literal[
    "always_approve",       # AI prepares; a human must approve every time
    "never",                # AI never does this — a human does it entirely
    "auto_below_threshold", # auto if amount <= threshold, else approve
    "auto_business_hours",  # auto during business hours, else approve
    "auto_if_trusted",      # auto only if the workspace is marked trusted
    "auto_always",          # full autonomy — no approval needed
]

_ALL_ACTIONS: tuple[str, ...] = (
    "content_generation", "campaign_creation", "campaign_launch",
    "social_publishing", "email_sending", "budget_change", "ad_creation",
    "ad_spending", "image_generation", "ai_recommendation", "ai_decision",
    "crm_update", "integration",
)


class ActionPolicy(BaseModel):
    mode: PolicyMode = "always_approve"
    threshold_amount: float | None = Field(
        default=None, ge=0, description="For auto_below_threshold: max amount auto-approved."
    )
    threshold_currency: str | None = Field(default=None, max_length=8)


class BusinessHours(BaseModel):
    enabled: bool = False
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=18, ge=0, le=23)
    timezone: str = Field(default="UTC", max_length=64)
    days: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4],
        description="Weekdays business hours apply (0=Mon … 6=Sun).",
    )


AutonomyLevel = Literal["manual", "assisted", "scheduled", "supervised", "full"]


class AutonomyPolicyConfig(BaseModel):
    """The resolved policy for a brand."""

    model_config = ConfigDict(from_attributes=True)

    autonomy_level: AutonomyLevel = "manual"
    default_mode: PolicyMode = "always_approve"
    policies: dict[str, ActionPolicy] = Field(default_factory=dict)
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    trusted: bool = False
    # Module 10 master switch (platform-wide). Reflected here so the UI can show
    # "autonomy is globally paused" even when a high level is configured.
    execution_enabled: bool = Field(
        default=False,
        description="Platform master switch. When false, NOTHING auto-runs regardless of level.",
    )
    updated_at: datetime | None = None
    configured: bool = Field(
        default=False, description="False when this is the safe default (no row saved yet)."
    )


class ApplyLevelRequest(BaseModel):
    level: AutonomyLevel


class AutonomyLevelInfo(BaseModel):
    key: str
    order: int
    label: str
    description: str


class AutonomyLevelsCatalog(BaseModel):
    levels: list[AutonomyLevelInfo]
    current: AutonomyLevel
    execution_enabled: bool


class AutonomyPolicyUpdate(BaseModel):
    default_mode: PolicyMode | None = None
    policies: dict[str, ActionPolicy] | None = None
    business_hours: BusinessHours | None = None
    trusted: bool | None = None


class PolicyDecision(BaseModel):
    """The outcome of evaluating the policy for one action."""

    action_type: str
    mode: PolicyMode
    allow_auto: bool = Field(description="True only when policy permits automatic execution now.")
    requires_approval: bool = Field(description="True when a human must approve before this runs.")
    reason: str


class CatalogEntry(BaseModel):
    key: str
    label: str
    description: str


class AutonomyCatalog(BaseModel):
    """Drives the settings UI — the governable actions + available modes."""

    action_types: list[CatalogEntry]
    modes: list[CatalogEntry]
