"""Phase 10.2b — Service-layer pure logic (no DB).

Covers:
  1. `materialise_matrix` — overlay of stored rows on code-defined
     defaults. Every (category × channel) cell present, lock invariant
     enforced even for stale rows.
  2. `coerce_updates_with_locks` — locked cells always enabled=True,
     duplicate updates de-duped (last write wins).

The end-to-end DB upsert path is exercised by the smoke test in
Phase 10.2b-7 against the real dev database; here we pin the logic
that doesn't need a session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aicmo.modules.notifications import catalog, service
from aicmo.modules.notifications.schemas import PreferenceUpdate


# ---------------------------------------------------------------------
#  materialise_matrix
# ---------------------------------------------------------------------


class TestMaterialiseMatrix:
    def test_empty_stored_returns_all_defaults(self) -> None:
        cells = service.materialise_matrix({})
        assert len(cells) == 18, "must produce all 6×3 cells"
        for c in cells:
            assert c.source == "system", (
                f"{c.category}/{c.channel} has source={c.source} but no stored row"
            )
            assert c.updated_at is None, (
                "system-default cells must report updated_at=None"
            )
            # The .enabled value must match catalog default.
            assert c.enabled is catalog.default_for(c.category, c.channel)

    def test_stored_row_overrides_default(self) -> None:
        now = datetime.now(timezone.utc)
        # Default: weekly_digest.email = True. Override to False.
        stored = {
            ("weekly_digest", "email"): service._StoredRow(
                enabled=False, source="user", updated_at=now
            )
        }
        cells = service.materialise_matrix(stored)
        cell = next(
            c for c in cells if c.category == "weekly_digest" and c.channel == "email"
        )
        assert cell.enabled is False
        assert cell.source == "user"
        assert cell.updated_at == now
        # Every other cell still matches default.
        for c in cells:
            if (c.category, c.channel) == ("weekly_digest", "email"):
                continue
            assert c.source == "system"

    def test_locked_cell_forced_true_even_if_stored_false(self) -> None:
        """Stale rows defence: if a row somehow has enabled=False on a
        locked cell (manual SQL, migration bug, race), the materialised
        matrix must still report it as True. The next upsert overwrites
        the stale row."""
        now = datetime.now(timezone.utc)
        stored = {
            ("billing_alert", "email"): service._StoredRow(
                enabled=False, source="user", updated_at=now
            )
        }
        cells = service.materialise_matrix(stored)
        billing_email = next(
            c
            for c in cells
            if c.category == "billing_alert" and c.channel == "email"
        )
        assert billing_email.enabled is True, (
            "locked cell must surface as True regardless of stored value"
        )
        assert billing_email.locked is True

    def test_locked_flag_set_on_locked_cells_only(self) -> None:
        cells = service.materialise_matrix({})
        locked_pairs = {(c.category, c.channel) for c in cells if c.locked}
        assert locked_pairs == {
            ("billing_alert", "email"),
            ("security_alert", "email"),
        }

    def test_cell_order_matches_catalog(self) -> None:
        """Frontend assumes matrix order = catalog order. Pin it."""
        cells = service.materialise_matrix({})
        produced = [(c.category, c.channel) for c in cells]
        expected = list(catalog.all_cells())
        assert produced == expected


# ---------------------------------------------------------------------
#  coerce_updates_with_locks
# ---------------------------------------------------------------------


class TestCoerceUpdatesWithLocks:
    def test_unlocked_cells_pass_through(self) -> None:
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(category="weekly_digest", channel="email", enabled=False),
                PreferenceUpdate(category="winner_alert", channel="slack", enabled=True),
            ]
        )
        assert out == {
            ("weekly_digest", "email"): False,
            ("winner_alert", "slack"): True,
        }

    def test_locked_billing_email_forced_true(self) -> None:
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(
                    category="billing_alert", channel="email", enabled=False
                )
            ]
        )
        assert out[("billing_alert", "email")] is True, (
            "locked billing email must NOT be disable-able"
        )

    def test_locked_security_email_forced_true(self) -> None:
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(
                    category="security_alert", channel="email", enabled=False
                )
            ]
        )
        assert out[("security_alert", "email")] is True

    def test_duplicate_updates_last_write_wins(self) -> None:
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(category="weekly_digest", channel="email", enabled=True),
                PreferenceUpdate(category="weekly_digest", channel="email", enabled=False),
            ]
        )
        # Both go to the same key — last value persists, locks aside.
        assert out == {("weekly_digest", "email"): False}

    def test_locked_cell_still_locked_after_dedup(self) -> None:
        """De-dup happens BEFORE lock coercion in the implementation,
        but the lock must still win at the end."""
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(
                    category="billing_alert", channel="email", enabled=True
                ),
                PreferenceUpdate(
                    category="billing_alert", channel="email", enabled=False
                ),
            ]
        )
        assert out[("billing_alert", "email")] is True

    def test_non_locked_billing_channels_can_be_disabled(self) -> None:
        """Only billing_alert.email is locked. Slack/SMS for billing are
        free — a user CAN mute slack billing alerts."""
        out = service.coerce_updates_with_locks(
            [
                PreferenceUpdate(category="billing_alert", channel="slack", enabled=False),
                PreferenceUpdate(category="billing_alert", channel="sms", enabled=False),
            ]
        )
        assert out == {
            ("billing_alert", "slack"): False,
            ("billing_alert", "sms"): False,
        }

    def test_empty_input_returns_empty_dict(self) -> None:
        assert service.coerce_updates_with_locks([]) == {}
