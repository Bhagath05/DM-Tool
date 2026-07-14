"""Pydantic schemas for organizations + memberships."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SLUG_RX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


# ---------------------------------------------------------------------
#  Organization
# ---------------------------------------------------------------------


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    owner_user_id: uuid.UUID
    status: str
    member_count: int
    brand_count: int
    created_at: datetime
    updated_at: datetime


class OrganizationList(BaseModel):
    items: list[OrganizationResponse]


class OrganizationCreate(BaseModel):
    """The frontend posts the org name + first-brand name in one shot.

    `brand_name` defaults to org name on the backend if omitted, which
    is what the single-form onboarding wizard uses.
    """

    name: str = Field(min_length=1, max_length=120)
    brand_name: str | None = Field(default=None, max_length=120)
    slug: str | None = Field(default=None, max_length=40)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must be lowercase letters, digits, and hyphens (no leading/trailing hyphen)"
            )
        return v


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class OrganizationCreateResult(BaseModel):
    """What POST /orgs returns — the new org + first brand + the
    caller's membership, all in one payload so the frontend can
    immediately set the active tenant headers."""

    organization: OrganizationResponse
    brand_id: uuid.UUID
    brand_slug: str
    member_id: uuid.UUID


# ---------------------------------------------------------------------
#  Onboarding wizard (W1-15)
# ---------------------------------------------------------------------


class OnboardingWorkspacePayload(BaseModel):
    """Single-shot wizard payload (W1-15 + A4).

    Required core: organization name+slug, brand name+slug. Slugs are
    auto-derived from names by the frontend wizard but the user can
    override before submit.

    Optional business-profile fields (A4): when ALL of `industry`,
    `target_audience`, `brand_tone`, `primary_goal`, and at least one
    `preferred_platform` are present, `create_workspace` also INSERTs
    a `BusinessProfile` in the same TX. Otherwise it skips the profile
    create and the user can complete that step later via the existing
    `/api/v1/business/onboarding` endpoint.

    Why optional: the A4 spec only requires Business Name, Brand Name,
    and Primary Goal to be strictly required at the UI layer. Other
    fields are user-skippable — the wizard advances even if they're
    blank. The server handles the resulting partial payload gracefully.
    """

    organization_name: str = Field(min_length=1, max_length=120)
    organization_slug: str = Field(min_length=1, max_length=40)
    brand_name: str = Field(min_length=1, max_length=120)
    brand_slug: str = Field(min_length=1, max_length=40)
    display_name: str | None = Field(default=None, max_length=120)

    # ---- A4 — optional business-profile bundle ----
    industry: str | None = Field(default=None, max_length=128)
    website: str | None = Field(default=None, max_length=512)
    brand_description: str | None = Field(default=None, max_length=2000)
    target_audience: str | None = Field(default=None, max_length=2000)
    primary_goal: str | None = Field(default=None, max_length=64)
    preferred_platforms: list[str] = Field(default_factory=list, max_length=15)
    brand_tone: str | None = Field(default=None, max_length=64)

    # ---- Persona segmentation (P-series, not an auth role) ----
    # Hint about who the user IS so the product can tailor copy + defaults.
    # NOT enforced for any permission decision. Keep allowed values in
    # sync with: alembic 0019 CHECK constraint AND the frontend
    # PERSONAS constant in onboarding-wizard.tsx.
    persona: (
        Literal[
            "solo_founder",
            "in_house_marketer",
            "agency",
            "freelancer",
            "consultant",
            "other",
        ]
        | None
    ) = Field(default=None)

    @field_validator("organization_slug", "brand_slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must be lowercase letters, digits, and hyphens "
                "(no leading/trailing hyphen, 1-40 chars)"
            )
        return v


class OnboardingWorkspaceResult(BaseModel):
    """Returned by POST /orgs/workspace.

    Carries every IDs the frontend's TenantProvider needs to immediately
    hydrate without a follow-up /me round-trip — though the wizard does
    refresh() anyway as a belt-and-braces consistency check.
    """

    organization_id: uuid.UUID
    organization_slug: str
    organization_name: str
    brand_id: uuid.UUID
    brand_slug: str
    brand_name: str
    member_id: uuid.UUID
    role_slugs: list[str]


# ---------------------------------------------------------------------
#  Membership
# ---------------------------------------------------------------------


class MemberResponse(BaseModel):
    """One row in the team page."""

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    role_slugs: list[str]
    last_active_brand_id: uuid.UUID | None
    joined_at: datetime
    status: str
    # Phase 6.6 Slice 4 — enterprise member management columns.
    last_active_at: datetime | None = None
    is_owner: bool = False


class MemberList(BaseModel):
    items: list[MemberResponse]


class MemberRoleUpdate(BaseModel):
    """Replace the member's role assignments wholesale.

    Caller posts the full list of role slugs that should be active.
    Server-side diff figures out what to add / remove.
    """

    role_slugs: list[str] = Field(min_length=1)


class MemberAssignRole(BaseModel):
    role_slug: str = Field(min_length=1)


# ---------------------------------------------------------------------
#  Errors / state changes
# ---------------------------------------------------------------------


OrgStatusFilter = Literal["active", "archived", "deleted", "all"]


# =====================================================================
#  Phase 10.2f — Organization profile + analytics
# =====================================================================
#
# Additive schemas for the Settings → Organization page. The existing
# `OrganizationResponse` stays unchanged so every prior caller keeps
# working; `OrganizationProfileRead` is the EXTENDED projection that
# includes the new profile fields.
#
# Hard rule (mirrors all 10.2 phases): no schema exposes secrets. The
# reflection guard in tests/orgs/test_profile_schemas.py enforces.

# ISO-3166 alpha-2 — uppercase, exactly two letters. Validated at the
# API boundary AND by the DB CHECK constraint (defence in depth).
_COUNTRY_RX = re.compile(r"^[A-Z]{2}$")

# IANA timezone shape. Full validation against the zoneinfo database
# is out of scope (would require shipping the zone list); we accept
# anything that LOOKS like an IANA zone: one or more segments of
# letters/digits/_/+/- separated by '/'. Examples allow `UTC`,
# `America/New_York`, `Etc/GMT+5`.
_TZ_RX = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z][A-Za-z0-9_+\-]*)*$")


class OrganizationProfileUpdate(BaseModel):
    """PATCH body for Settings → Organization → profile.

    Every field is optional. Sending None for a field LEAVES IT
    UNCHANGED (we don't have a way for the API to express "clear this
    to NULL" via an absent key — Pydantic can't distinguish missing
    from None). To clear a field, send an empty string; the service
    layer normalises empty strings to NULL.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=512)
    website: str | None = Field(default=None, max_length=512)
    industry: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)
    # No min_length — empty string is the explicit 'clear this field'
    # signal, normalised to NULL by the service layer. The regex validator
    # below enforces the 2-letter ISO-3166 alpha-2 format when a value
    # IS supplied.
    country: str | None = Field(default=None, max_length=2)

    @field_validator("country")
    @classmethod
    def _validate_country(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        v = v.upper()
        if not _COUNTRY_RX.match(v):
            raise ValueError(
                "country must be an ISO-3166 alpha-2 code (e.g. 'US', 'IN')"
            )
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if not _TZ_RX.match(v):
            raise ValueError(
                "timezone must look like an IANA zone (e.g. 'UTC', 'America/New_York')"
            )
        return v

    @field_validator("logo_url", "website")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class OrganizationProfileRead(BaseModel):
    """Extended GET projection — superset of OrganizationResponse with
    the 10.2f profile fields. Phase 10.2g (frontend wiring) consumes
    this on the Settings → Organization page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    owner_user_id: uuid.UUID
    status: str
    member_count: int
    brand_count: int
    created_at: datetime
    updated_at: datetime
    # Phase 10.2f additions
    logo_url: str | None
    website: str | None
    industry: str | None
    timezone: str | None
    country: str | None


class OrganizationAnalytics(BaseModel):
    """GET /orgs/{id}/analytics — aggregate counts for the Settings →
    Organization overview tiles.

    This is the "Analytics foundation" objective: a single endpoint the
    page hits to render member/brand/invite totals + activity. NOT a
    metrics dashboard — those live in the Performance Intelligence
    Engine, which is untouched in Phase 10.2f.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    brand_count: int
    active_brand_count: int
    member_count: int
    pending_invite_count: int
    created_at: datetime
    last_activity_at: datetime | None = Field(
        default=None,
        description=(
            "Most recent of: last audit_log entry, last sign-in event "
            "for any member. None if neither has fired yet."
        ),
    )


# =====================================================================
#  Danger zone — reset & delete
# =====================================================================
#
# Two owner-only destructive operations surfaced in Settings → Organization:
#
#   POST /orgs/{id}/reset  → wipe USER-PROVIDED content (business profile,
#                            campaigns, content, leads, creatives, …) but
#                            keep the workspace shell (org + members +
#                            roles + brands + billing + connections).
#                            Returns `OrganizationResetResult`.
#   POST /orgs/{id}/purge  → HARD delete the org row; ON DELETE CASCADE
#                            removes every tenant child. Irreversible.
#                            Returns a bare {"status": "purged"}.


class OrganizationResetResult(BaseModel):
    """What POST /orgs/{id}/reset returns.

    `details` maps each cleared table → row count, so the UI (and the
    audit trail) can show exactly what was removed.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    tables_cleared: int
    rows_deleted: int
    details: dict[str, int] = Field(default_factory=dict)
