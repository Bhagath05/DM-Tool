"""Phase 10.2d — Pydantic schemas for team management.

Hard rule (mirrored from prior phases): no schema exposes secrets,
tokens, or hashed credentials. The reflection guard in
`tests/team/test_schemas.py` enforces — this includes the invite
`token_hash` (a SHA-256 we never want a frontend to see).

The single exception is `InviteCreateResponse.accept_url`, which DOES
contain the raw token. That's intentional and the whole point — it's
the one-time return value. The schema name + field docstring make this
explicit so a future "let me cache this" PR is a visible review item.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------
#  Enums — lock-step with migration 0026 CHECK constraints
# ---------------------------------------------------------------------

InviteStatus = Literal["pending", "accepted", "revoked", "expired"]

# Roles that can be GRANTED by invite via the Phase 10.2d API surface.
# Matches the 4-role canonical catalog minus owner. `editor` is a legacy
# role retained in the DB CHECK constraint (migration 0026) for any
# pre-10.2d code path that writes it directly, but is NOT exposed via
# the API — admins inviting "editor" via the API would surprise the
# spec'd 4-role UX. Tested by `tests/team/test_role_catalog.py`.
InvitableRole = Literal["admin", "analyst", "viewer"]

# Roles surfaced on the Settings → Team page. 'editor' is omitted from
# the UI list (kept in DB for backward compat with pre-10.2d orgs).
CanonicalRole = Literal["owner", "admin", "analyst", "viewer"]


# ---------------------------------------------------------------------
#  Role catalog (descriptors for UI)
# ---------------------------------------------------------------------


class RoleDescriptor(BaseModel):
    """Display + policy metadata for one role.

    `can_be_invited_as` is the SINGLE field the frontend should consult
    when rendering the "Invite teammate → role" dropdown. Don't infer
    from `slug` — invitability is a policy decision that may evolve
    independently from the role's identity.
    """

    model_config = ConfigDict(extra="forbid")

    slug: CanonicalRole
    display_name: str
    description: str
    capabilities: list[str] = Field(
        description="Plain-language capability bullets the UI renders under the role.",
    )
    can_be_invited_as: bool
    can_be_granted_by_admin: bool = Field(
        description="True if a non-owner admin can grant this role.",
    )
    is_terminal_for_org: bool = Field(
        description=(
            "Owner is terminal — you can't have an org without one. "
            "Drives the 'cannot revoke last owner' UI affordance."
        ),
    )


class RoleCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[RoleDescriptor]


# ---------------------------------------------------------------------
#  Members (read-side projection of OrganizationMember + roles)
# ---------------------------------------------------------------------


class MemberSummary(BaseModel):
    """One row in the Team page table. Joins user + member + roles."""

    model_config = ConfigDict(extra="forbid")

    member_id: UUID
    user_id: UUID
    email: str
    display_name: str | None
    role_slugs: list[str]
    is_owner: bool
    joined_at: datetime
    last_active_at: datetime | None = Field(
        default=None,
        description=(
            "Last seen via auth — derived from user_session.last_seen_at "
            "where available. Null when we have no session record yet."
        ),
    )


# ---------------------------------------------------------------------
#  Invites
# ---------------------------------------------------------------------


class InviteCreate(BaseModel):
    """Body for POST /team/invites.

    Email is validated by EmailStr; the service layer lowercases +
    trims before insert. Role must be one of the four invitable roles
    — Pydantic Literal rejects 'owner' before the service even runs.
    """

    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role_slug: InvitableRole


class InviteRead(BaseModel):
    """Public projection of an invite row. Does NOT include token_hash."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    email: str
    role_slug: InvitableRole
    status: InviteStatus
    invited_by_user_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    is_expired: bool = Field(
        description="True if expires_at < now, regardless of status column.",
    )


class InviteCreateResponse(BaseModel):
    """Single endpoint where the raw invite URL is returned.

    `accept_url` is the ONLY surface that carries the raw token. The
    server discards the raw token immediately after constructing this
    response; only `sha256(token)` is persisted. If the caller doesn't
    capture this URL, the invite is unrecoverable — re-issue is the
    only path.
    """

    model_config = ConfigDict(extra="forbid")

    invite: InviteRead
    accept_url: str = Field(
        description=(
            "Full URL for the invitee to click. Contains the raw token as "
            "the path/query component. Returned ONCE — never persisted."
        ),
    )


class InviteList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invites: list[InviteRead]


# ---------------------------------------------------------------------
#  Invite acceptance (server-driven, no tenant header)
# ---------------------------------------------------------------------


class InvitePreview(BaseModel):
    """GET /invites/{token} — public-ish preview for the acceptance UI.

    Returns the org name + role about to be assigned, so the page can
    show "Accept invite to ACME as Analyst?" without revealing
    membership / member counts / billing.
    """

    model_config = ConfigDict(extra="forbid")
    organization_name: str
    organization_slug: str
    role_slug: InvitableRole
    role_display_name: str
    invited_email: str
    expires_at: datetime
    is_expired: bool


class InviteAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=128)


class InviteAcceptResponse(BaseModel):
    """Returned from POST /invites/accept.

    `next_route` tells the frontend where to redirect after acceptance
    (typically the dashboard with the new org pre-selected).
    """

    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    brand_id: UUID | None = Field(
        default=None,
        description=(
            "If the org has exactly one brand, we auto-select it for the "
            "new member's `last_active_brand_id`. None if the org has 0 "
            "or 2+ brands — frontend must show a brand picker."
        ),
    )
    role_slugs: list[str]
    next_route: str = Field(
        description="Suggested redirect path after acceptance.",
    )


# ---------------------------------------------------------------------
#  Aggregated team overview (one call → renders the whole page)
# ---------------------------------------------------------------------


class TeamOverview(BaseModel):
    """GET /team — everything Settings → Team needs to render in one call."""

    model_config = ConfigDict(extra="forbid")

    members: list[MemberSummary]
    pending_invites: list[InviteRead]
    roles: list[RoleDescriptor]
    member_count: int
    pending_invite_count: int
    can_invite: bool = Field(
        description="True if the requester holds `team.manage`. Drives UI affordances.",
    )
    can_revoke_owner: bool = Field(
        description=(
            "True if requester is an owner AND there is more than one "
            "owner. Drives the 'demote owner' affordance."
        ),
    )
