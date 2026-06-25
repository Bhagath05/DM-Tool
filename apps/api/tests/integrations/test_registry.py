"""Phase 10.2a — IntegrationRegistry semantics.

Importing `aicmo.modules.integrations.providers` registers all six
providers as a side effect. Tests that exercise registration / dedup
semantics save & restore the registry around themselves so the
state survives for the rest of the suite.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import (
    DuplicateProvider,
    IntegrationRegistry,
    UnknownProvider,
)


# Ensure the providers module is imported so stubs self-register.
import aicmo.modules.integrations.providers  # noqa: F401, E402


@pytest.fixture(autouse=True)
def _restore_registry():
    """Snapshot the registry before each test and restore after, so
    tests that mutate it (register / reset) don't bleed into others."""
    snapshot = dict(IntegrationRegistry._providers)
    yield
    IntegrationRegistry._providers = snapshot


def test_all_six_phase_10_2_providers_registered() -> None:
    slugs = {p.slug for p in IntegrationRegistry.all()}
    expected = {
        "meta_ads",
        "google_ads",
        "linkedin_ads",
        "tiktok_ads",
        "hubspot",
        "salesforce",
    }
    assert expected <= slugs, f"missing: {expected - slugs}"


def test_all_phase_10_2_providers_are_stubs() -> None:
    """Phase 10.2a ships every provider as a stub (available=False).
    Phase 11 lights up Meta first."""
    for p in IntegrationRegistry.all():
        if p.slug in {"meta_ads", "google_ads", "linkedin_ads", "tiktok_ads", "hubspot", "salesforce"}:
            assert p.available is False, (
                f"{p.slug} reports available=True in Phase 10.2a — "
                "did Phase 11 land?"
            )


def test_all_returns_stable_alphabetic_order_within_category() -> None:
    all_providers = IntegrationRegistry.all()
    keys = [(p.category, p.display_name.lower()) for p in all_providers]
    assert keys == sorted(keys), "registry.all() must be stable-sorted"


def test_get_known_slug() -> None:
    meta = IntegrationRegistry.get("meta_ads")
    assert meta.display_name == "Meta Ads"
    assert meta.category == "ads"


def test_get_unknown_slug_raises_unknown_provider() -> None:
    with pytest.raises(UnknownProvider, match="bogus"):
        IntegrationRegistry.get("bogus")


def test_has_predicate() -> None:
    assert IntegrationRegistry.has("meta_ads") is True
    assert IntegrationRegistry.has("definitely_not_a_provider") is False


def test_register_rejects_empty_slug() -> None:
    class _Bad(StubProvider):
        slug = ""
        display_name = "Bad"
        category: ClassVar[str] = "ads"  # type: ignore[assignment]
        icon_id = "bad"
        description = "..."
        scopes: ClassVar[list[str]] = []

    with pytest.raises(ValueError, match="empty slug"):
        IntegrationRegistry.register(_Bad())


def test_register_rejects_duplicate_slug() -> None:
    class _DupeA(StubProvider):
        slug = "_dupe_test"
        display_name = "A"
        category = "ads"
        icon_id = "a"
        description = "a"
        scopes: ClassVar[list[str]] = []

    class _DupeB(StubProvider):
        slug = "_dupe_test"
        display_name = "B"
        category = "ads"
        icon_id = "b"
        description = "b"
        scopes: ClassVar[list[str]] = []

    IntegrationRegistry.register(_DupeA())
    with pytest.raises(DuplicateProvider, match="_dupe_test"):
        IntegrationRegistry.register(_DupeB())


def test_register_same_instance_twice_is_idempotent() -> None:
    """Re-importing a provider module (e.g. during hot reload) should
    not raise — same instance, same slug = no-op."""
    p = IntegrationRegistry.get("meta_ads")
    IntegrationRegistry.register(p)
    IntegrationRegistry.register(p)
    assert IntegrationRegistry.get("meta_ads") is p
