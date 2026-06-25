"""Pydantic schemas for the users module.

The most-called endpoint in the entire frontend is `/api/v1/me`. Its
response carries: the user, their memberships, each membership's
brands + role + permissions, and a `suggested_route` so the wrapper
page knows where to send a returning user.

Single round-trip on every page load — keep it tight.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------
#  User
# ---------------------------------------------------------------------


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clerk_user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    status: str
    last_seen_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------------
#  Membership tree (one per org the user belongs to)
# ---------------------------------------------------------------------


class BrandSummary(BaseModel):
    """Compact brand info embedded inside membership."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    status: str


class OrgSummary(BaseModel):
    """Compact org info embedded inside membership."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    status: str
    member_count: int
    brand_count: int


class MembershipResponse(BaseModel):
    """One membership = one org the user belongs to, plus everything
    the frontend needs to render the org-switcher / brand-switcher /
    role badge without further round-trips."""

    organization: OrgSummary
    role_slugs: list[str]
    permissions: list[str]
    brands: list[BrandSummary]
    last_active_brand_id: uuid.UUID | None
    joined_at: datetime


# ---------------------------------------------------------------------
#  Resolved-active-tenant snapshot
# ---------------------------------------------------------------------


class ActiveTenant(BaseModel):
    """What the resolver computed for THIS request — handy for frontend
    debugging and for the active-org/brand badge in the topbar."""

    organization_id: uuid.UUID
    brand_id: uuid.UUID | None
    role_slugs: list[str]
    permissions: list[str]


# ---------------------------------------------------------------------
#  The big one
# ---------------------------------------------------------------------


SuggestedRoute = Literal[
    "/dashboard",
    "/onboarding",
    "/orgs/select",
]


class MeResponse(BaseModel):
    """Top-level / payload returned by GET /api/v1/me.

    `suggested_route` is the redirect target for the `/onboarding`
    wrapper page — encapsulates the routing matrix on the backend so the
    frontend doesn't reinvent it.

    `active` is populated only if the request carried valid X-Org-Id +
    X-Brand-Id headers. On first load, it's None and the frontend uses
    `suggested_route`.
    """

    user: UserResponse
    memberships: list[MembershipResponse]
    active: ActiveTenant | None
    suggested_route: SuggestedRoute
