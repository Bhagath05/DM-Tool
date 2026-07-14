"""Phase 6.6 Slice 2 — ALLOW/DENY/INHERIT permission engine.

Pins the pure resolver `resolve_effects` (the merge logic across a member's
roles). The DB join in compute_permissions_for_member delegates to it, so this
covers the semantics without a database."""

from __future__ import annotations

from aicmo.tenancy.permissions import resolve_effects


def test_allow_only_is_the_union_backward_compatible():
    # Pre-6.6 state: every row is 'allow' → same union as before.
    granted = resolve_effects([("crm.view", "allow"), ("crm.manage", "allow")])
    assert granted == frozenset({"crm.view", "crm.manage"})


def test_explicit_deny_overrides_allow():
    # One role allows crm.manage, another denies it → denied wins.
    granted = resolve_effects([("crm.manage", "allow"), ("crm.manage", "deny")])
    assert "crm.manage" not in granted


def test_deny_only_grants_nothing():
    assert resolve_effects([("lead.export", "deny")]) == frozenset()


def test_inherit_is_absence_and_grants_nothing():
    # A permission with no pair is INHERIT → not granted on its own.
    granted = resolve_effects([("content.create", "allow")])
    assert "content.edit" not in granted  # never mentioned → inherited → off


def test_multi_role_merge_allows_the_union_minus_denies():
    # Role A: allow view+manage. Role B: allow export, deny manage.
    granted = resolve_effects([
        ("crm.view", "allow"), ("crm.manage", "allow"),
        ("lead.export", "allow"), ("crm.manage", "deny"),
    ])
    assert granted == frozenset({"crm.view", "lead.export"})


def test_empty_grants_nothing():
    assert resolve_effects([]) == frozenset()
