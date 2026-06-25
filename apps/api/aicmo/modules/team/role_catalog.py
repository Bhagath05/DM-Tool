"""Phase 10.2d — Canonical role catalog.

Single source of truth for what the Settings → Team UI shows. The
backend authorization layer reads from the DB (roles + permissions
tables); this file is the DISPLAY layer's source of truth.

If you add a permission to a role here without updating the migration
seed, the displayed capability list and the actual capability diverge
— a confusing bug. Always update both in the same PR.

Why this exists separately from the DB seed:
  - Migrations are append-only; the seed describes one historical state.
    This file is the live, current truth.
  - Display copy ("Manage all team members and content") doesn't belong
    in the database — it changes for UX reasons without RBAC changes.
  - Policy flags like `can_be_granted_by_admin` are display hints; the
    actual gate is in `aicmo/modules/orgs/service.py:assign_role`.
"""

from __future__ import annotations

from aicmo.modules.team.schemas import RoleCatalog, RoleDescriptor


_ROLES: tuple[RoleDescriptor, ...] = (
    RoleDescriptor(
        slug="owner",
        display_name="Owner",
        description=(
            "Full control over the workspace. Only an existing owner can "
            "grant or revoke the owner role, and the last owner can never "
            "be removed."
        ),
        capabilities=[
            "Everything an admin can do",
            "Manage billing + subscription",
            "Transfer ownership to another member",
            "Delete the workspace",
        ],
        can_be_invited_as=False,  # never invite as owner
        can_be_granted_by_admin=False,
        is_terminal_for_org=True,
    ),
    RoleDescriptor(
        slug="admin",
        display_name="Admin",
        description=(
            "Manage the team, brands, content, and integrations. Cannot "
            "modify owners or change billing."
        ),
        capabilities=[
            "Invite + remove members (except owners)",
            "Create and edit brands",
            "Manage content + campaigns + integrations",
            "View leads + analytics",
        ],
        can_be_invited_as=True,
        can_be_granted_by_admin=True,
        is_terminal_for_org=False,
    ),
    RoleDescriptor(
        slug="analyst",
        display_name="Analyst",
        description=(
            "Read-only access to workspace data, plus the ability to "
            "export leads for offline analysis. Cannot create content "
            "or change anything."
        ),
        capabilities=[
            "View analytics + dashboards",
            "View + export leads",
            "Browse the asset library",
        ],
        can_be_invited_as=True,
        can_be_granted_by_admin=True,
        is_terminal_for_org=False,
    ),
    RoleDescriptor(
        slug="viewer",
        display_name="Viewer",
        description=(
            "Read-only. See dashboards, leads, and the asset library. "
            "Cannot export, create, or change anything."
        ),
        capabilities=[
            "View analytics + dashboards",
            "View leads",
            "Browse the asset library",
        ],
        can_be_invited_as=True,
        can_be_granted_by_admin=True,
        is_terminal_for_org=False,
    ),
)


def get_catalog() -> RoleCatalog:
    """Return the static catalog. Same for every user, every org."""
    return RoleCatalog(roles=list(_ROLES))


def descriptor_for(slug: str) -> RoleDescriptor | None:
    """Look up one descriptor. Returns None for unknown slug
    (caller decides whether to 404)."""
    for r in _ROLES:
        if r.slug == slug:
            return r
    return None


# Frozen sets for O(1) lookup at runtime.
_INVITABLE_SLUGS: frozenset[str] = frozenset(
    r.slug for r in _ROLES if r.can_be_invited_as
)
_ADMIN_GRANTABLE_SLUGS: frozenset[str] = frozenset(
    r.slug for r in _ROLES if r.can_be_granted_by_admin
)


def is_invitable(slug: str) -> bool:
    """True if a role can be granted via the invite flow.

    Owner is the only False — owner is conferred at workspace creation
    or via the (future) transfer-ownership flow, never by invite.
    """
    return slug in _INVITABLE_SLUGS


def is_admin_grantable(slug: str) -> bool:
    """True if a non-owner admin can grant this role.

    Admins cannot grant owner. They can grant admin / analyst /
    viewer to anyone except an existing owner.
    """
    return slug in _ADMIN_GRANTABLE_SLUGS
