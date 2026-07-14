"""Phase 6.6 Slice 3 — Role Management backend logic.

Hermetic: no DB. Covers the schema contracts (slug guarding, color
semantics, reorder shape) and the query-light service branches
(`reorder_roles` skipping system roles, `_audit_summary`). The
query-heavy paths (create/update/duplicate reconciliation) are exercised
against real Postgres at Render boot + the danger-zone integration test.
"""

from __future__ import annotations

import types
import uuid

import pytest

from aicmo.modules.rbac import service
from aicmo.modules.rbac.schemas import (
    RoleCreate,
    RoleDuplicate,
    RoleReorder,
    RoleReorderItem,
    RoleUpdate,
)

# ---------------------------------------------------------------------
#  Schema contracts
# ---------------------------------------------------------------------


def test_role_create_defaults_allow_deny_empty() -> None:
    r = RoleCreate(slug="growth_lead", name="Growth Lead")
    assert r.permission_slugs == []
    assert r.deny_slugs == []
    assert r.priority == 0
    assert r.color is None


@pytest.mark.parametrize(
    "slug",
    ["owner", "admin", "marketing_manager", "analyst", "viewer", "editor"],
)
def test_role_create_rejects_reserved_system_slug(slug: str) -> None:
    with pytest.raises(ValueError, match="system role"):
        RoleCreate(slug=slug, name="X")


@pytest.mark.parametrize("slug", ["Bad-Slug", "1leading", "ab", "has space"])
def test_role_create_rejects_malformed_slug(slug: str) -> None:
    with pytest.raises(ValueError):
        RoleCreate(slug=slug, name="X")


def test_role_duplicate_guards_reserved_slug() -> None:
    with pytest.raises(ValueError, match="system role"):
        RoleDuplicate(slug="admin", name="Copy of Admin")
    # A fresh slug is accepted.
    assert RoleDuplicate(slug="admin_copy", name="Copy").slug == "admin_copy"


def test_role_update_color_absent_vs_clear() -> None:
    """`color` distinguishes 'not provided' from 'clear it'. The service
    keys off model_fields_set, so the schema must preserve that signal."""
    absent = RoleUpdate(name="X")
    assert "color" not in absent.model_fields_set

    clear = RoleUpdate(color="")
    assert "color" in clear.model_fields_set
    assert clear.color == ""

    setc = RoleUpdate(color="#ff0000")
    assert setc.color == "#ff0000"


def test_role_reorder_requires_at_least_one_item() -> None:
    with pytest.raises(ValueError):
        RoleReorder(items=[])


# ---------------------------------------------------------------------
#  _audit_summary
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("role.created", "Role created"),
        ("role.updated", "Role updated"),
        ("role.deleted", "Role deleted"),
        ("role.reordered", "Roles reordered"),
        ("member.role_assigned", "Assigned to a member"),
        ("member.role_removed", "Removed from a member"),
        ("something.else", "something.else"),  # unknown → passthrough
    ],
)
def test_audit_summary(action: str, expected: str) -> None:
    evt = types.SimpleNamespace(action=action)
    assert service._audit_summary(evt) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------------
#  reorder_roles — the multi-tenant safety invariant
# ---------------------------------------------------------------------


class _FakeSession:
    """Just enough AsyncSession surface for reorder_roles."""

    def __init__(self, rows: dict[uuid.UUID, object]) -> None:
        self._rows = rows
        self.flushed = False

    async def get(self, _model: object, pk: uuid.UUID) -> object | None:
        return self._rows.get(pk)

    async def flush(self) -> None:
        self.flushed = True


def _role(*, is_system: bool, org_id: uuid.UUID | None, priority: int) -> object:
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        slug=f"role_{priority}",
        is_system=is_system,
        organization_id=org_id,
        priority=priority,
    )


@pytest.mark.asyncio
async def test_reorder_reprices_custom_roles_only(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid.uuid4()
    custom = _role(is_system=False, org_id=org, priority=10)
    system = _role(is_system=True, org_id=None, priority=100)
    other_org = _role(is_system=False, org_id=uuid.uuid4(), priority=5)
    rows = {custom.id: custom, system.id: system, other_org.id: other_org}
    session = _FakeSession(rows)

    recorded: list[dict] = []

    async def _fake_record(_s, **kw):
        recorded.append(kw)

    async def _fake_list_roles(_s, **_kw):
        return ["sentinel"]

    monkeypatch.setattr(service.audit_service, "record", _fake_record)
    monkeypatch.setattr(service, "list_roles", _fake_list_roles)

    result = await service.reorder_roles(
        session,  # type: ignore[arg-type]
        actor_user_id=uuid.uuid4(),
        organization_id=org,
        payload=RoleReorder(
            items=[
                RoleReorderItem(role_id=custom.id, priority=50),
                RoleReorderItem(role_id=system.id, priority=1),
                RoleReorderItem(role_id=other_org.id, priority=1),
            ]
        ),
    )

    # Only the org's own custom role is repriced.
    assert custom.priority == 50
    assert system.priority == 100  # system role untouched
    assert other_org.priority == 5  # different org untouched
    assert session.flushed is True
    assert recorded and recorded[0]["action"] == "role.reordered"
    assert recorded[0]["after"] == {"reordered": ["role_10"]}
    assert result == ["sentinel"]


@pytest.mark.asyncio
async def test_reorder_noop_skips_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    org = uuid.uuid4()
    custom = _role(is_system=False, org_id=org, priority=20)
    session = _FakeSession({custom.id: custom})

    recorded: list[dict] = []

    async def _fake_record(_s, **kw):
        recorded.append(kw)

    async def _fake_list_roles(_s, **_kw):
        return []

    monkeypatch.setattr(service.audit_service, "record", _fake_record)
    monkeypatch.setattr(service, "list_roles", _fake_list_roles)

    # Priority already 20 → no change → no flush, no audit.
    await service.reorder_roles(
        session,  # type: ignore[arg-type]
        actor_user_id=uuid.uuid4(),
        organization_id=org,
        payload=RoleReorder(items=[RoleReorderItem(role_id=custom.id, priority=20)]),
    )
    assert session.flushed is False
    assert recorded == []
