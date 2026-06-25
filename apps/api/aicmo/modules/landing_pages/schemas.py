from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# ---------- content schema (the JSONB shape) ----------


class Benefit(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=400)
    icon: str | None = Field(
        default=None,
        max_length=32,
        description="Optional lucide-react icon name, e.g. 'sparkles', 'zap'.",
    )


class SocialProof(BaseModel):
    quote: str = Field(min_length=4, max_length=400)
    author: str = Field(min_length=1, max_length=80)
    role: str | None = Field(default=None, max_length=120)


class FAQItem(BaseModel):
    q: str = Field(min_length=2, max_length=240)
    a: str = Field(min_length=2, max_length=1000)


class FormField(BaseModel):
    """Renderer config for one input on the lead form."""

    name: str = Field(
        pattern=r"^[a-z][a-z0-9_]{0,30}$",
        description="Snake_case identifier — what the lead-capture API sees.",
    )
    label: str = Field(min_length=1, max_length=80)
    type: Literal["text", "email", "tel", "textarea"] = "text"
    required: bool = True
    placeholder: str | None = Field(default=None, max_length=120)


class LandingPageContent(BaseModel):
    """The on-page conversion structure. Stored as JSONB."""

    headline: str = Field(min_length=4, max_length=160)
    subheadline: str | None = Field(default=None, max_length=400)
    benefits: list[Benefit] = Field(default_factory=list, max_length=6)
    cta_text: str = Field(min_length=2, max_length=40, default="Get started")
    form_fields: list[FormField] = Field(
        min_length=1,
        max_length=8,
        description="At least one field — typically email. Order matters for render.",
    )
    social_proof: list[SocialProof] = Field(default_factory=list, max_length=6)
    faq: list[FAQItem] = Field(default_factory=list, max_length=10)
    footer_text: str | None = Field(default=None, max_length=400)
    # Optional rich elements
    privacy_blurb: str | None = Field(
        default=None,
        max_length=200,
        description="Small-print disclosure under the form, e.g. 'No spam. Unsubscribe anytime.'",
    )


# ---------- API request / response ----------


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_RESERVED = frozenset(
    {
        "api",
        "app",
        "admin",
        "static",
        "public",
        "p",
        "assets",
        "auth",
        "sign-in",
        "sign-up",
        "_next",
    }
)


def _validate_slug(v: str) -> str:
    if len(v) < 3 or len(v) > 80:
        raise ValueError("Slug must be 3-80 characters")
    if not SLUG_RE.match(v):
        raise ValueError("Slug must be lowercase letters, digits, and hyphens")
    if v in SLUG_RESERVED:
        raise ValueError("That slug is reserved — pick another")
    return v


class LandingPageCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(
        default=None,
        description="Custom slug — auto-generated from title if omitted.",
    )
    content: LandingPageContent
    redirect_url: HttpUrl | None = None

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        return _validate_slug(v) if v is not None else None


class LandingPageUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = None
    content: LandingPageContent | None = None
    redirect_url: HttpUrl | None = None
    status: Literal["draft", "published"] | None = None
    is_archived: bool | None = None

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        return _validate_slug(v) if v is not None else None


class LandingPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    slug: str
    title: str
    status: Literal["draft", "published"]
    preview_token: str
    content: LandingPageContent
    redirect_url: str | None
    view_count: int
    submission_count: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class LandingPageList(BaseModel):
    items: list[LandingPageResponse]


# Public-facing variant — strips internal fields the public renderer doesn't need.
class PublicLandingPage(BaseModel):
    slug: str
    title: str
    content: LandingPageContent
    redirect_url: str | None
    # Site-key passed through so the front-end can render the Turnstile widget.
    turnstile_site_key: str | None
