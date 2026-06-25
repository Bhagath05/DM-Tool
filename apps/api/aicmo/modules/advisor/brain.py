"""Business Brain — canonical business context for the intelligence engine."""

from __future__ import annotations

from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

from pydantic import BaseModel, Field


class BusinessBrain(BaseModel):
    industry: str
    business_type: str
    target_audience: str
    monthly_budget: str | None = None
    growth_goal: str | None = None
    location: str | None = None
    competitors: list[str] = Field(default_factory=list)
    business_name: str | None = None
    preferred_platforms: list[str] = Field(default_factory=list)


def load_business_brain(profile: BusinessProfile | BusinessProfileResponse) -> BusinessBrain:
    """Map profile row → Business Brain. Never fabricates values."""
    if isinstance(profile, BusinessProfileResponse):
        return BusinessBrain(
            industry=profile.industry,
            business_type=profile.business_type or profile.industry,
            target_audience=profile.target_audience,
            monthly_budget=profile.monthly_budget_band,
            growth_goal=profile.primary_goal_text
            or (profile.goals[0] if profile.goals else None),
            location=profile.business_location,
            competitors=list(profile.competitors or []),
            business_name=profile.business_name,
            preferred_platforms=list(profile.preferred_platforms or []),
        )
    return BusinessBrain(
        industry=profile.industry,
        business_type=profile.business_type or profile.industry,
        target_audience=profile.target_audience,
        monthly_budget=profile.monthly_budget_band,
        growth_goal=profile.primary_goal_text
        or (profile.goals[0] if profile.goals else None),
        location=profile.business_location,
        competitors=list(profile.competitors or []),
        business_name=profile.business_name,
        preferred_platforms=list(profile.preferred_platforms or []),
    )


def brain_completeness(brain: BusinessBrain) -> tuple[int, list[str]]:
    """Score 0–7 and list missing setup steps."""
    steps: list[str] = []
    score = 0
    if brain.industry.strip():
        score += 1
    else:
        steps.append("Set your industry")
    if brain.business_type.strip():
        score += 1
    else:
        steps.append("Set your business type")
    if len(brain.target_audience.strip()) >= 10:
        score += 1
    else:
        steps.append("Describe your target audience")
    if brain.monthly_budget:
        score += 1
    else:
        steps.append("Set your monthly marketing budget")
    if brain.growth_goal:
        score += 1
    else:
        steps.append("Set your primary growth goal")
    if brain.location:
        score += 1
    else:
        steps.append("Add your business location")
    if brain.competitors:
        score += 1
    else:
        steps.append("Add at least one competitor")
    return score, steps


def brain_has_minimum(brain: BusinessBrain) -> bool:
    """Minimum to generate any recommendation."""
    return bool(brain.industry.strip()) and len(brain.target_audience.strip()) >= 10


def brain_to_prompt_block(brain: BusinessBrain) -> str:
    lines = [
        f"Business: {brain.business_name or 'Unknown'}",
        f"Industry: {brain.industry}",
        f"Business type: {brain.business_type}",
        f"Target audience: {brain.target_audience}",
    ]
    if brain.monthly_budget:
        lines.append(f"Monthly budget band: {brain.monthly_budget}")
    if brain.growth_goal:
        lines.append(f"Growth goal: {brain.growth_goal}")
    if brain.location:
        lines.append(f"Location: {brain.location}")
    if brain.competitors:
        lines.append(f"Competitors: {', '.join(brain.competitors[:10])}")
    if brain.preferred_platforms:
        lines.append(f"Preferred platforms: {', '.join(brain.preferred_platforms)}")
    return "\n".join(lines)
