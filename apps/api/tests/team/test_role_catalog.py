"""Phase 10.2d — Role catalog correctness.

The catalog is the contract the frontend renders against. Pin every
field so a copy edit doesn't quietly change a capability bullet, and
pin the policy flags (invitable, admin-grantable) so a regression
that lets admins invite as owner fails CI loudly.
"""

from __future__ import annotations

from aicmo.modules.team import role_catalog


# ---------------------------------------------------------------------
#  Surface
# ---------------------------------------------------------------------


def test_exactly_four_canonical_roles() -> None:
    """The Settings → Team page renders these four — pinned. If we ever
    decide to surface 'editor' too, this test changes deliberately."""
    slugs = [r.slug for r in role_catalog.get_catalog().roles]
    assert slugs == ["owner", "admin", "analyst", "viewer"]


def test_every_role_has_display_copy() -> None:
    for r in role_catalog.get_catalog().roles:
        assert r.display_name, f"{r.slug} missing display_name"
        assert r.description and len(r.description) >= 30, (
            f"{r.slug} description too short to render usefully"
        )
        assert r.capabilities, f"{r.slug} has no capability bullets"


# ---------------------------------------------------------------------
#  Invitability — SECURITY CRITICAL
# ---------------------------------------------------------------------


def test_owner_is_NOT_invitable() -> None:
    """Owner is conferred at workspace creation or via the (future)
    transfer-ownership flow — never via invite. Loosening this lets
    anyone with team.manage make themselves owner via a self-invite +
    email trickery."""
    assert role_catalog.is_invitable("owner") is False


def test_admin_analyst_viewer_are_invitable() -> None:
    for slug in ("admin", "analyst", "viewer"):
        assert role_catalog.is_invitable(slug) is True


def test_editor_NOT_exposed_via_phase_10_2d_api() -> None:
    """`editor` existed pre-10.2d and is retained in the migration
    CHECK constraint so direct DB writes still work, but the Phase
    10.2d catalog + InvitableRole Literal deliberately exclude it.
    Loosening this means inviting as editor through /team/invites,
    which contradicts the spec'd 4-role surface (owner/admin/analyst/
    viewer). If the product genuinely wants editor back on the UI,
    add it to BOTH `role_catalog._ROLES` and `InvitableRole` in the
    same PR — this test fails until both move together."""
    assert role_catalog.is_invitable("editor") is False
    assert role_catalog.descriptor_for("editor") is None


def test_admin_cannot_grant_owner() -> None:
    """Mirror of the assign_role rule in orgs/service.py. Pinned here
    so the catalog stays in lock-step with the enforcement layer."""
    assert role_catalog.is_admin_grantable("owner") is False


def test_admin_can_grant_admin_analyst_viewer() -> None:
    for slug in ("admin", "analyst", "viewer"):
        assert role_catalog.is_admin_grantable(slug) is True, (
            f"admin should be able to grant {slug}"
        )


# ---------------------------------------------------------------------
#  Terminal-for-org
# ---------------------------------------------------------------------


def test_owner_is_terminal_for_org() -> None:
    """An org cannot exist without an owner. The last-owner safety
    check in `remove_role` enforces this; the catalog flag drives the
    UI affordance."""
    desc = role_catalog.descriptor_for("owner")
    assert desc is not None and desc.is_terminal_for_org is True


def test_non_owner_roles_are_not_terminal() -> None:
    for slug in ("admin", "analyst", "viewer"):
        desc = role_catalog.descriptor_for(slug)
        assert desc is not None and desc.is_terminal_for_org is False


# ---------------------------------------------------------------------
#  Lookup helpers
# ---------------------------------------------------------------------


def test_descriptor_for_unknown_returns_none() -> None:
    """Unknown slugs return None — don't raise. Caller decides
    whether to 404."""
    assert role_catalog.descriptor_for("not-a-role") is None
