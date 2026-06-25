"""Phase 10.2b — Catalog correctness.

The catalog is the contract the frontend renders against. Pin every
visible field so a copy edit doesn't quietly break a settings page.
"""

from __future__ import annotations

from aicmo.modules.notifications import catalog


# ---------------------------------------------------------------------
#  Category surface
# ---------------------------------------------------------------------


def test_exactly_six_categories() -> None:
    cat = catalog.get_catalog()
    ids = [c.id for c in cat.categories]
    assert ids == [
        "weekly_digest",
        "winner_alert",
        "campaign_alert",
        "billing_alert",
        "security_alert",
        "system_alert",
    ], "category order is the canonical render order — don't reorder lightly"


def test_every_category_has_display_copy() -> None:
    for c in catalog.get_catalog().categories:
        assert c.display_name, f"{c.id} missing display_name"
        assert c.description, f"{c.id} missing description"
        assert len(c.description) >= 20, (
            f"{c.id} description is too short to be useful in UI"
        )


def test_every_category_has_at_least_email_default() -> None:
    """A user who flips no switches should still receive email digests
    for every category. Anything else would silently mute notifications
    behind a hidden default."""
    for c in catalog.get_catalog().categories:
        assert "email" in c.default_channels, (
            f"{c.id} doesn't ship with email enabled by default"
        )


# ---------------------------------------------------------------------
#  Channel surface
# ---------------------------------------------------------------------


def test_exactly_three_channels() -> None:
    cat = catalog.get_catalog()
    ids = [c.id for c in cat.channels]
    assert ids == ["email", "slack", "sms"]


def test_every_channel_is_placeholder_in_phase_10_2b() -> None:
    """Phase 10.2b ships preferences without delivery. The UI relies on
    this flag to surface honest 'coming soon' affordances. When a
    dispatcher ships in a later phase this test changes to allow
    'available' for that specific channel — flagging the canary."""
    for ch in catalog.get_catalog().channels:
        assert ch.delivery_status == "placeholder", (
            f"{ch.id} reports delivery_status={ch.delivery_status} — "
            "did the dispatcher ship?"
        )
        assert ch.pending_reason, (
            f"{ch.id} is a placeholder but has no pending_reason copy"
        )


# ---------------------------------------------------------------------
#  Locks (CRITICAL)
# ---------------------------------------------------------------------


def test_billing_email_is_locked() -> None:
    assert catalog.is_locked("billing_alert", "email") is True, (
        "billing email lock loosened — security regression"
    )


def test_security_email_is_locked() -> None:
    assert catalog.is_locked("security_alert", "email") is True, (
        "security email lock loosened — security regression"
    )


def test_only_billing_and_security_email_are_locked() -> None:
    """Pin the lock surface exhaustively. Any new lock added without
    updating this test means someone tightened the policy silently."""
    locked = {
        (cat, ch)
        for cat in catalog.all_category_ids()
        for ch in catalog.all_channel_ids()
        if catalog.is_locked(cat, ch)
    }
    assert locked == {
        ("billing_alert", "email"),
        ("security_alert", "email"),
    }


def test_locked_cells_are_also_defaults() -> None:
    """A cell can't be locked-on if it isn't default-on — that would
    create an unreachable state."""
    for cat in catalog.all_category_ids():
        for ch in catalog.all_channel_ids():
            if catalog.is_locked(cat, ch):
                assert catalog.default_for(cat, ch), (
                    f"{cat}/{ch} is locked but not default-on — bug"
                )


# ---------------------------------------------------------------------
#  Iteration helpers
# ---------------------------------------------------------------------


def test_all_cells_yields_exactly_eighteen() -> None:
    """6 categories × 3 channels = 18 cells. The matrix endpoint
    materialises against this — pin the count so an enum addition
    forces an intentional test update."""
    cells = list(catalog.all_cells())
    assert len(cells) == 18
    assert len(set(cells)) == 18, "duplicate cells in all_cells()"


def test_all_cells_canonical_order() -> None:
    """The matrix is sorted by category-first, then channel — so the
    frontend can render rows of channels grouped under each category."""
    cells = list(catalog.all_cells())
    cat_order = [c.id for c in catalog.get_catalog().categories]
    ch_order = [c.id for c in catalog.get_catalog().channels]
    expected = [(cat, ch) for cat in cat_order for ch in ch_order]
    assert cells == expected


# ---------------------------------------------------------------------
#  Sanity
# ---------------------------------------------------------------------


def test_default_for_known_pair() -> None:
    assert catalog.default_for("winner_alert", "email") is True
    assert catalog.default_for("winner_alert", "sms") is False
    assert catalog.default_for("billing_alert", "slack") is False


def test_default_for_unknown_pair_is_false() -> None:
    """Unknown ids must NOT raise — they return False. Defensive: any
    code path that synthesises bogus ids should fail-closed (off),
    not crash."""
    assert catalog.default_for("nonexistent", "email") is False
    assert catalog.default_for("weekly_digest", "carrier_pigeon") is False
